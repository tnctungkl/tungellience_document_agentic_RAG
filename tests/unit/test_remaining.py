import json
import sys
import types
from urllib import request as urllib_request

import numpy as np
import pytest

from app.core.exceptions import GenerationError
from app.llm.base import StaticLLM
from app.llm.local_llm import OllamaLLM
from app.rag.context_builder import build_context
from app.rag.generator import RAGGenerator
from app.rag.prompt import build_rag_prompt
from app.validation.schemas import DocumentChunk, SearchResult
from app.analytics.evaluator import RAGEvaluator
from app.analytics.metrics import compute_retrieval_metrics
from app.retrieval.reranker import LexicalReranker


def _result(text='annual leave policy'):
    from uuid import uuid4
    chunk = DocumentChunk(document_id=uuid4(), chunk_index=0, text=text, metadata={'file_name':'hr.txt','source_path':'/safe/hr.txt'})
    return SearchResult(chunk=chunk, vector_score=0.9)


def test_context_and_prompt():
    results=[_result()]
    contexts, sources = build_context(results)
    assert contexts == ['annual leave policy']
    assert sources == ['hr.txt']
    assert '[SOURCE 1]' in build_rag_prompt('policy?', contexts)


def test_generator_empty_and_response():
    assert 'could not find enough' in RAGGenerator(StaticLLM()).generate('q', [])
    assert RAGGenerator(StaticLLM('answer')).generate('q', [_result()]) == 'answer'


def test_static_llm_and_local_llm(monkeypatch):
    llm = StaticLLM('ok')
    assert llm.generate('prompt') == 'ok'
    payload = json.dumps({'message': {'content': 'generated'}, 'response': ''}).encode()

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self): return payload

    monkeypatch.setattr(urllib_request, 'urlopen', lambda *args, **kwargs: FakeResponse())
    assert OllamaLLM('http://localhost:11434','model').generate('q') == 'generated'

    def failing(*args, **kwargs): raise OSError('offline')
    monkeypatch.setattr(urllib_request, 'urlopen', failing)
    with pytest.raises(GenerationError, match='Cannot connect to Ollama'):
        OllamaLLM('http://localhost:11434','model').generate('q')


def test_reranker_empty_tokens():
    reranker = LexicalReranker()
    assert reranker.score('', 'text') == 0.0
    assert reranker.score('text', '') == 0.0


def test_metrics_empty():
    metrics = compute_retrieval_metrics([])
    assert metrics.hit_rate == 0.0
    assert metrics.mean_reciprocal_rank == 0.0


def test_evaluator(vector_runtime):
    _, _, manager = vector_runtime
    from app.validation.schemas import DocumentChunk
    from uuid import uuid4
    chunk = DocumentChunk(document_id=uuid4(), chunk_index=0, text='annual leave policy', metadata={'file_name':'hr.txt'})
    manager.add_chunks([chunk])
    from app.retrieval.retriever import Retriever
    retriever = Retriever(manager, LexicalReranker(), -1.0, 0.0)
    metrics = RAGEvaluator(retriever, top_k=1, rerank_top_k=1).evaluate([{'query':'annual leave','expected_chunk_id':str(chunk.id)}])
    assert metrics.hit_rate == 1.0


def test_sentence_transformer_backend_with_fake_module(monkeypatch):
    class FakeModel:
        def __init__(self, name): self.name=name
        def get_sentence_embedding_dimension(self): return 3
        def encode(self, texts, **kwargs): return np.array([[1., 2., 2.] for _ in texts], dtype=np.float32)
    fake_module = types.SimpleNamespace(SentenceTransformer=FakeModel)
    monkeypatch.setitem(sys.modules, 'sentence_transformers', fake_module)
    from app.embeddings.model import SentenceTransformerEmbeddingModel
    model = SentenceTransformerEmbeddingModel('fake', 3)
    assert np.isclose(np.linalg.norm(model.embed(['x'])[0]), 1.0)


def test_reranker_orders_relevant_result_first():
    reranker = LexicalReranker()
    ranked = reranker.rerank('annual leave', [_result('python backend'), _result('annual leave policy details')], 2)
    assert ranked[0].chunk.text.startswith('annual leave')
