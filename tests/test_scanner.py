from datetime import date

import pytest

from wipecord import config
from wipecord.client import ApiResult, DiscordError
from wipecord.scanner import ChannelInfo, Mode, ScanCriteria, Scanner, summarise

from fakes import FakeClient, message, search_page

GUILD = ChannelInfo(id="C1", name="general", is_dm=False, guild_id="G1")
DM = ChannelInfo(id="C9", name="Alice", is_dm=True)


def scan(client, channel=GUILD, criteria=None):
    scanner = Scanner(client, "ME")
    return list(scanner.scan(channel, criteria or ScanCriteria())), scanner


# --- the absolute rule: only the token owner's messages ----------------------


def test_messages_from_other_users_are_never_returned():
    client = FakeClient(
        search_pages=[
            search_page(
                [
                    message("1", author_id="ME", content="mine"),
                    message("2", author_id="OTHER", content="theirs"),
                    message("3", author_id="ME", content="mine too"),
                ],
                total=3,
            )
        ]
    )
    found, _ = scan(client)
    assert [ref.id for ref in found] == ["1", "3"]


def test_the_author_filter_is_also_sent_to_the_server():
    client = FakeClient(search_pages=[search_page([])])
    scan(client)
    assert client.search_calls[0]["author_id"] == "ME"


def test_context_messages_from_others_are_dropped_even_when_unflagged():
    # A hit arrives with surrounding context; the context is not ours to delete.
    client = FakeClient(
        search_pages=[
            ApiResult(
                status=200,
                data={
                    "total_results": 1,
                    "messages": [
                        [
                            message("10", author_id="OTHER", hit=False),
                            message("11", author_id="ME", hit=True),
                            message("12", author_id="OTHER", hit=False),
                        ]
                    ],
                },
                headers={},
            )
        ]
    )
    found, _ = scan(client)
    assert [ref.id for ref in found] == ["11"]


def test_the_same_message_is_not_returned_twice_across_overlapping_pages():
    # A large total keeps paging alive; the overlap is what is under test.
    page = search_page([message("1"), message("2")], total=100)
    client = FakeClient(search_pages=[page, search_page([message("2"), message("3")], total=100)])
    found, _ = scan(client)
    assert [ref.id for ref in found] == ["1", "2", "3"]


# --- modes -------------------------------------------------------------------


def test_last_n_stops_as_soon_as_the_count_is_reached():
    client = FakeClient(
        search_pages=[search_page([message(str(i)) for i in range(1, 11)], total=100)]
    )
    found, _ = scan(client, criteria=ScanCriteria(mode=Mode.LAST_N, limit=4))
    assert len(found) == 4


def test_a_date_range_is_pushed_to_the_server_as_snowflake_bounds():
    client = FakeClient(search_pages=[search_page([])])
    criteria = ScanCriteria(
        mode=Mode.DATE_RANGE, start_date=date(2024, 1, 1), end_date=date(2024, 1, 31)
    )
    scan(client, criteria=criteria)
    call = client.search_calls[0]
    assert call["min_id"] is not None and call["max_id"] is not None
    assert call["min_id"] < call["max_id"]


def test_messages_outside_the_requested_window_are_rejected_client_side():
    criteria = ScanCriteria(
        mode=Mode.DATE_RANGE, start_date=date(2024, 1, 1), end_date=date(2024, 1, 2)
    )
    min_id, max_id = criteria.bounds()
    client = FakeClient(
        search_pages=[
            search_page(
                [
                    message(str(min_id - 5000)),  # older than the range
                    message(str(min_id + 1000)),  # inside
                    message(str(max_id + 5000)),  # newer than the range
                ],
                total=3,
            )
        ]
    )
    found, _ = scan(client, criteria=criteria)
    assert [ref.id for ref in found] == [str(min_id + 1000)]


def test_pinned_messages_are_skipped_by_default():
    client = FakeClient(
        search_pages=[search_page([message("1"), message("2", pinned=True)], total=2)]
    )
    found, _ = scan(client)
    assert [ref.id for ref in found] == ["1"]


def test_pinned_messages_are_included_when_the_filter_is_turned_off():
    client = FakeClient(
        search_pages=[search_page([message("1"), message("2", pinned=True)], total=2)]
    )
    found, _ = scan(client, criteria=ScanCriteria(skip_pinned=False))
    assert [ref.id for ref in found] == ["1", "2"]


# --- search mechanics --------------------------------------------------------


def test_a_dm_search_omits_the_guild_scope():
    client = FakeClient(search_pages=[search_page([])])
    scan(client, channel=DM)
    assert client.search_calls[0]["guild_id"] is None


def test_a_warming_search_index_is_waited_out_rather_than_treated_as_failure():
    client = FakeClient(
        search_pages=[
            ApiResult(status=202, data={"code": config.SEARCH_INDEX_NOT_READY, "retry_after": 1}, headers={}),
            search_page([message("1")], total=1),
        ]
    )
    found, scanner = scan(client)
    assert [ref.id for ref in found] == ["1"]
    assert scanner.used_fallback is False


def test_paging_stops_once_the_reported_total_is_consumed():
    pages = [search_page([message(str(i)) for i in range(25)], total=25)]
    client = FakeClient(search_pages=pages)
    found, scanner = scan(client)
    assert len(found) == 25
    assert scanner.total_hint == 25
    assert len(client.search_calls) == 1


def test_the_total_is_exposed_for_the_progress_bar():
    client = FakeClient(search_pages=[search_page([message("1")], total=460)])
    _, scanner = scan(client)
    assert scanner.total_hint == 460


def test_the_offset_ceiling_slides_the_window_instead_of_paging_deeper():
    # Fill up to the offset ceiling, then one more page, then exhaustion.
    per_page = config.SEARCH_PAGE_SIZE
    pages_to_ceiling = config.SEARCH_MAX_OFFSET // per_page
    # Distinct, descending ids across pages, the way real search results arrive.
    pages = [
        search_page(
            [message(str(1_000_000 - page * per_page - i)) for i in range(per_page)],
            total=999_999,
        )
        for page in range(pages_to_ceiling)
    ]
    pages.append(search_page([], total=999_999))
    client = FakeClient(search_pages=pages)
    scanner = Scanner(client, "ME")
    list(scanner.scan(GUILD, ScanCriteria()))
    # The last call restarted at offset 0 with a tightened max_id.
    last = client.search_calls[-1]
    assert last["offset"] == 0
    assert last["max_id"] is not None


# --- fallback ----------------------------------------------------------------


def test_history_pagination_takes_over_when_search_fails():
    client = FakeClient(
        search_pages=[DiscordError(400, "search not available")],
        history_pages=[
            [message("3", author_id="ME"), message("2", author_id="OTHER"), message("1")],
            [],
        ],
    )
    found, scanner = scan(client)
    assert scanner.used_fallback is True
    assert [ref.id for ref in found] == ["3", "1"]


def test_the_fallback_still_refuses_other_peoples_messages():
    client = FakeClient(
        search_pages=[DiscordError(400, "nope")],
        history_pages=[[message(str(i), author_id="OTHER") for i in range(5)], []],
    )
    found, _ = scan(client)
    assert found == []


def test_the_fallback_stops_once_it_passes_the_lower_date_bound():
    criteria = ScanCriteria(
        mode=Mode.DATE_RANGE, start_date=date(2024, 1, 1), end_date=date(2024, 1, 31)
    )
    min_id, _ = criteria.bounds()
    client = FakeClient(
        search_pages=[DiscordError(400, "nope")],
        history_pages=[
            [message(str(min_id + 100)), message(str(min_id - 100)), message(str(min_id - 200))],
            [],
        ],
    )
    found, _ = scan(client, criteria=criteria)
    assert [ref.id for ref in found] == [str(min_id + 100)]
    # It returned instead of requesting another page.
    assert len(client.history_calls) == 1


def test_the_fallback_pages_backwards_using_the_oldest_id_seen():
    client = FakeClient(
        search_pages=[DiscordError(400, "nope")],
        history_pages=[[message("30"), message("20")], [message("10")], []],
    )
    scan(client)
    assert client.history_calls[1]["before"] == "20"


# --- channel description -----------------------------------------------------


def test_a_guild_channel_is_labelled_with_a_hash():
    scanner = Scanner(FakeClient(), "ME")
    info = scanner.describe_channel("C1")
    assert info.is_dm is False
    assert info.label == "#general"
    assert info.guild_id == "G1"


def test_a_dm_is_labelled_with_the_other_persons_name():
    client = FakeClient(
        channel={"id": "C9", "type": 1, "recipients": [{"id": "U2", "global_name": "Alice"}]}
    )
    info = Scanner(client, "ME").describe_channel("C9")
    assert info.is_dm is True
    assert info.label == "Alice"
    assert info.guild_id is None


def test_an_inaccessible_channel_surfaces_the_error():
    client = FakeClient(channel=DiscordError(403, "Missing Access"))
    with pytest.raises(DiscordError):
        Scanner(client, "ME").describe_channel("C1")


# --- summaries ---------------------------------------------------------------


def test_a_summary_collapses_newlines_and_truncates():
    text = summarise({"content": "line one\nline two " + "x" * 100})
    assert "\n" not in text
    assert len(text) <= 60


def test_an_attachment_only_message_still_gets_a_readable_summary():
    assert "attachment" in summarise({"content": "", "attachments": [{}, {}]})
    assert summarise({"content": ""}) == "[no text]"
