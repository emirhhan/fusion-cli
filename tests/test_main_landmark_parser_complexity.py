"""Bound actual parser stack work without flaky wall-clock thresholds."""

import pytest

from fusion_cli.engines.agent.web_verify import _MainLandmarkParser


class CountingAncestors(list):
    def __init__(self, values):
        super().__init__(values)
        self.reads = 0

    def __getitem__(self, index):
        self.reads += 1
        return super().__getitem__(index)

    def pop(self, index=-1):
        self.reads += 1
        return super().pop(index)


@pytest.mark.parametrize("size", [100, 500])
def test_unknown_closers_do_not_rescan_all_open_ancestors(size):
    parser = _MainLandmarkParser()
    parser.feed("<div>" * size)
    ancestors = CountingAncestors(parser._ancestors)
    parser._ancestors = ancestors
    parser.feed("</not-open>" * size)
    assert ancestors.reads <= 2 * size
    assert len(ancestors) == size
    parser.feed("</div>" * size)
    assert ancestors.reads <= 4 * size
    assert not ancestors


def test_matching_ancestor_cleanup_restores_visible_landmark_context():
    parser = _MainLandmarkParser()
    parser.feed("<div hidden><div><template><main>sample</main>")
    assert not parser.found
    # Close the inner div through the still-open template; the outer hidden div remains.
    parser.feed("</div><main>hidden</main>")
    assert not parser.found
    parser.feed("</div><main>visible</main>")
    assert parser.found
    assert not parser._ancestors


def test_popped_descendant_tag_cannot_match_a_later_spurious_closer():
    parser = _MainLandmarkParser()
    parser.feed("<div><template><section>sample</div>")
    assert not parser._ancestors
    parser.feed("<div hidden></template><main>hidden</main>")
    assert not parser.found
    parser.feed('</div><div role="main">visible</div>')
    assert parser.found
    assert not parser._ancestors
