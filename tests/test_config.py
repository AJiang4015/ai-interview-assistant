def test_large_scale_rag_settings_defaults():
    from app.config import Settings
    s = Settings(_env_file=None,
                 bailian_api_key="x", siliconflow_api_key="y",
                 jwt_secret="test-secret")
    assert s.vector_index_type == "hnsw"
    assert s.hnsw_m == 16
    assert s.hnsw_ef_search == 64
    assert s.sparse_backend == "auto"
    assert s.concurrent_batches == 4
    assert s.enable_parent_expansion is True