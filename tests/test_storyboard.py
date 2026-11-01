import pytest

from deadinternet.domain.experiment import Beat
from deadinternet.storyboard import (
    UnsafeId,
    check_segment,
    read_storyboard,
    storyboard_path,
    video_path,
    write_storyboard,
)


def test_round_trip_keeps_the_hash(tmp_path):
    beats = (
        Beat(spoken="Open.", on_screen="Now", visual_note="wide"),
        Beat(spoken="Close.", on_screen="", visual_note=""),
    )
    path = storyboard_path(tmp_path, "history", "art-of-war", "exp-1")
    assert video_path(tmp_path, "history", "art-of-war", "exp-1") == path.with_name("exp-1.mp4")
    digest = write_storyboard(path, beats)
    loaded, again = read_storyboard(path)
    assert loaded == beats
    assert again == digest


@pytest.mark.parametrize("segment", ["", " ", ".", "..", "a/b", "a\\b"])
def test_path_segments_reject_escapes(segment):
    with pytest.raises(UnsafeId):
        check_segment(segment)
