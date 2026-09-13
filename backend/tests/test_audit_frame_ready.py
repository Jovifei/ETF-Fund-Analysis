"""Slow JS must not accept user edits before the host protocol is bound."""
from html.parser import HTMLParser

from app.workspace.original_board import original_board_frame


def test_original_frame_controls_wait_for_authenticated_host_state():
    class Controls(HTMLParser):
        def __init__(self):
            super().__init__()
            self.found = {}
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get('id') in {'searchInput', 'horizonSelect'}:
                self.found[attrs['id']] = attrs
    parser = Controls()
    parser.feed(original_board_frame().body.decode('utf-8'))
    assert set(parser.found) == {'searchInput', 'horizonSelect'}
    assert all('disabled' in attrs for attrs in parser.found.values())
