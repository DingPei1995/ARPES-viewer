"""
loader -- reading data in, and keeping it.

``registry`` decides who reads a file and applies the load-time axis
options; ``scan`` is what every reader returns (``NxsScan``, the kinds and
their axis slots) and the lazy arrays that keep a measurement on disk;
``beamlines`` holds one reader per beamline (``antares`` for SOLEIL
ANTARES; copy ``beamlines/alba.py`` to add an HDF5 one); ``formats`` what
several of them share (NeXus layouts, Scienta SES files); ``native`` writes
and reads this program's own saved format; ``session`` is
where a computed dataset is written the moment it exists.

Nothing in here imports Qt.
"""
