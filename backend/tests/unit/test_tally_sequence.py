from test_tally_export import make_log

from app.services.tally_export import build_tally_xml


def test_repository_sequence_and_list_produce_identical_export():
    logs = [make_log(), make_log(with_rzp=False)]
    assert build_tally_xml(tuple(logs)) == build_tally_xml(logs)
