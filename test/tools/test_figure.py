"""The figure composer's page: spans, pictures, the page height."""
import numpy as np
import pytest

from arpes_viewer.tools.output import figure as F


# --------------------------------------------------------------------------
# Spans, pictures in their own shape, a page that follows its panels
# --------------------------------------------------------------------------
def _data_panel():
    return F.Panel(data=F.PanelData(array=np.ones((10, 8)),
                                    x=np.linspace(0, 1, 10),
                                    y=np.linspace(0, 1, 8)))


def test_a_panel_can_span_grid_cells():
    picture = F.Panel(data=F.picture_data(np.zeros((100, 200, 4), np.uint8)),
                      span=(1, 2))
    panels = [picture] + [_data_panel() for _ in range(4)]
    figure = F.Figure(panels)
    assert F.Figure.span_cells(panels, 3) == [
        (0, 0, 1, 2), (0, 2, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1), (1, 2, 1, 1)]
    figure.freeze()
    figure.arrange_grid(2, 3)
    one = panels[1].frame
    wide = picture.frame
    assert wide[2] > 1.4 * one[2]                      # more than one cell
    assert wide[3] == pytest.approx(one[3])            # as tall as the row
    assert wide[3] == pytest.approx(wide[2] * 0.5)     # its own shape
    assert panels[2].frame[1] > one[1]                 # next row


def test_the_page_follows_a_panel_moved_by_hand():
    figure = F.Figure([_data_panel(), _data_panel()], rows=1, cols=2)
    figure.freeze()
    before = figure.style.height_mm
    x, y, w, h = figure.panels[1].frame
    figure.move_panel(figure.panels[1], (x, y + 40.0, w, h))
    assert figure.style.height_mm > before + 30.0
    figure.move_panel(figure.panels[1], (x, y, w, h))
    assert figure.style.height_mm == pytest.approx(before, abs=3.0)


def test_inner_tick_numbers_keep_room_for_them():
    figure = F.Figure([_data_panel(), _data_panel()], rows=1, cols=2)
    figure.style.edge_labels_only = True
    figure.style.inner_tick_numbers = True
    assert not figure.shows_y_labels(1)                # the name: edges only
    left, *_ = figure.margins_mm()
    assert left > 0
