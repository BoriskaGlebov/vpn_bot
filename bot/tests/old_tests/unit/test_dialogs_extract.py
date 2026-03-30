import pytest

from bot.dialogs.dialogs_text import extract_knowledge_chunks


@pytest.mark.dialogs
@pytest.mark.parametrize(
    "data,min_list_length,min_str_length,expected_len",
    [
        # simple long string qualifies
        ("a" * 200, 100, 150, 1),
        # short string filtered out
        ("short text", 100, 150, 0),
        # list of strings combined qualifies
        (["a" * 60, "b" * 60], 100, 150, 1),
        # list of strings too short after join
        (["a" * 20, "b" * 20], 100, 150, 0),
    ],
)
def test_extract_basic_variants(data, min_list_length, min_str_length, expected_len):
    chunks = extract_knowledge_chunks(
        data,
        parent_key="root",
        min_list_length=min_list_length,
        min_str_length=min_str_length,
    )
    assert len(chunks) == expected_len
    for ch in chunks:
        assert set(ch.keys()) == {"source", "content"}
        assert isinstance(ch["content"], str)
        assert isinstance(ch["source"], str)


@pytest.mark.dialogs
def test_extract_from_nested_dict_and_lists():
    data = {
        "section": {
            "intro": "x" * 160,  # long string -> 1 chunk
            "bullets": [  # list[str] long enough -> 1 chunk
                "line1 " * 10,
                "line2 " * 10,
                "line3 " * 10,
            ],
            "mixed": [  # mixed list: recurse elements
                "y" * 160,  # qualifies as str chunk
                {"deep": ["a" * 60, "b" * 60]},  # list[str] qualifies
            ],
        }
    }

    chunks = extract_knowledge_chunks(
        data,
        parent_key="",
        min_list_length=100,
        min_str_length=150,
    )

    # Expect: intro (section.intro), bullets (section.bullets), mixed str (section.mixed), deep list (section.mixed.deep)
    assert len(chunks) == 4
    sources = {c["source"] for c in chunks}
    assert {
        "section.intro",
        "section.bullets",
        "section.mixed",
        "section.mixed.deep",
    } <= sources


@pytest.mark.dialogs
def test_extract_ignores_unsupported_types():
    class X:
        pass

    data = {"a": X(), "b": 123, "c": None}
    chunks = extract_knowledge_chunks(data, parent_key="root")
    assert chunks == []


@pytest.mark.dialogs
def test_extract_trims_and_counts_length_correctly():
    # string with spaces around still qualifies after strip
    data = {"text": " " + ("z" * 151) + "  \n"}
    chunks = extract_knowledge_chunks(data, parent_key="art", min_str_length=150)
    assert len(chunks) == 1
    assert chunks[0]["source"] == "art.text"
    assert chunks[0]["content"].startswith("z")


@pytest.mark.dialogs
def test_extract_list_of_mixed_recurse_path_propagates():
    data = {
        "chapter": [
            {"part": "x" * 160},
            {"part": ["a" * 60, "b" * 60]},
            ["skip", "too short"],  # list[str] too short -> ignored
        ]
    }

    chunks = extract_knowledge_chunks(
        data, parent_key="book", min_list_length=100, min_str_length=150
    )
    # Got from chapter.part (str) and chapter.part (list[str])
    assert len(chunks) == 2
    assert all(c["source"].startswith("book.chapter") for c in chunks)
