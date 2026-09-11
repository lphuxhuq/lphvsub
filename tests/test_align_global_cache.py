from autodub.pipeline_cache import AlignGlobalCache


def test_align_global_cache_store_and_lookup(tmp_path):
    db_file = tmp_path / "alignments.db"
    cache = AlignGlobalCache(custom_db=db_file)

    words = [("Xin", 0.0, 0.2), ("chào", 0.2, 0.5)]
    cache.store("key_1", words)

    result = cache.lookup("key_1")
    assert result is not None
    assert len(result) == 2
    assert result[0] == ("Xin", 0.0, 0.2)
    assert result[1] == ("chào", 0.2, 0.5)

    assert cache.lookup("non_existent_key") is None


def test_align_global_cache_batch_lookup_and_store(tmp_path):
    db_file = tmp_path / "alignments.db"
    cache = AlignGlobalCache(custom_db=db_file)

    items = [
        ("key_a", [("A", 0.0, 0.1)]),
        ("key_b", [("B", 0.1, 0.2)]),
        ("key_c", [("C", 0.2, 0.3)]),
    ]
    cache.store_batch(items)

    hits = cache.lookup_batch(["key_a", "key_c", "key_missing"])
    assert len(hits) == 2
    assert "key_a" in hits
    assert "key_c" in hits
    assert "key_missing" not in hits
    assert hits["key_a"][0] == ("A", 0.0, 0.1)


def test_align_global_cache_corruption_recovery(tmp_path):
    db_file = tmp_path / "alignments.db"
    db_file.write_bytes(b"CORRUPTED SQLITE HEADER")

    cache = AlignGlobalCache(custom_db=db_file)
    # Looking up corrupted file should gracefully return None
    assert cache.lookup("any_key") is None

    # Storing new item should heal and re-create valid db
    cache.store("key_healed", [("word", 0.0, 0.5)])
    healed_res = cache.lookup("key_healed")
    assert healed_res is not None
    assert healed_res[0] == ("word", 0.0, 0.5)
