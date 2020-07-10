#!/usr/bin/env python

"""
Very Simple script to compare the contents of two Evtgen PDL files in a visual
way. It creates an html file with the content of the pdl file in a table. The
table will only contain the names and ids for all particles and the values that
actually changed between the two files.
"""

import argparse
import logging
import difflib
import math
from collections import namedtuple
from xml.etree import ElementTree as ET

class Particle(namedtuple("Particle", ["name", "id", "mass", "width", "max_dM", "charge",
                                       "spin", "lifetime", "pythiaId", "line"])):
    """
    Class to keep all the values from the pdl file and addition
    the line number this particle was found
    """
    #: Types of the fields for proper conversion
    TYPES=[str, int, float, float, float, int, int, float, int, int]
    #: Don't create instance dictionaries, all slots are defined in the parent class
    __slots__ = ()

    def __eq__(self, other):
        """Check for equality of the particle by just considering id"""
        return self[1] == other[1]

    def __hash__(self):
        """Make the class hashable considering only id"""
        return hash(self[1])

    def diff(self, other, tolerance=1e-5):
        """
        Return a dictionary with the differences to another particle This will
        return a dictionary with the name of all properties that are not equal
        between both particles mapped to both values, first the one from this
        particle, then the one from the other particle

        This function will ignore a change in line number
        """
        def isclose(a, b):
            if isinstance(a, float):
                return math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance)
            return a==b
        return {f:(a,b) for f, a, b in zip(self._fields[:-1], self, other) if not isclose(a, b)}

def parse_evtpdl(name):
    """Parse an evt.pdl file from Evtgen and return a list of Particle instances"""
    particles = []
    with open(name) as f:
        for nr, line in enumerate(f):
            if line.startswith('*'):
                continue
            if not line.strip():
                continue
            values = line.split()
            if values[0] == "end":
                break
            if values[:3] != ['add', 'p', 'Particle']:
                logging.error("line %d starts with unexpected token: %s", nr, line)
                continue
            values = line.split()[3:] + [nr]
            particles.append(Particle(*[convert(e) for convert, e in zip(Particle.TYPES, values)]))
    return particles

class PDLDiffTable:
    """Create an html table containing the content of a PDL
    file and its comparision to a second PDL file"""
    def __init__(self, fileA, fileB, order="name", tolerance=1e-5, precision=5):
        self.fileA = fileA
        self.fileB = fileB
        self.order = order.lower()
        self.precision = precision
        self.tolerance = tolerance
        if self.order not in ('id', 'name', 'a', 'b'):
            raise RuntimeError(f'unknown sort order: {self.order}, choose one of id, name, A, B')

        self._table = ET.Element("table")
        thead = ET.SubElement(ET.SubElement(self._table, "thead"), 'tr')
        for col in ['what', 'name', 'id', 'property', f'value in {fileA}',
                    f'value in {fileB}', f'line in {fileA}', f'line in {fileB}']:
            ET.SubElement(thead, 'th').text = col
        self._tbody = ET.SubElement(self._table, "tbody")
        self._lastparticle = None

    def _add_row(self, what, name, id, property, valueA, valueB, lineA, lineB):
        """Add a row to the table

        * format values with the given precision
        * skip particle name/id for consecutive values for the same particle
        * set the classes 'changed', 'added', 'removed' for the cells.
        """
        if isinstance(valueA, float):
            valueA = f'{valueA:.{self.precision}g}'
        if isinstance(valueB, float):
            valueB = f'{valueB:.{self.precision}g}'

        row = [what, name, id, property, valueA, valueB, lineA, lineB]
        rowclass = "newparticle"
        classes = [what]*8

        if self._lastparticle == [name, id]:
            row = ['', '', '', property, valueA, valueB, '', '']
            classes = ['', '', '', what, what, what, '', '']
            rowclass = ""

        if what == 'changed':
            classes[4] = 'removed'
            classes[5] = 'added'

        tr = ET.SubElement(self._tbody, 'tr', attrib={'class':rowclass})
        for r,c in zip(row, classes):
            ET.SubElement(tr, 'td', attrib={'class':c}).text=str(r)

        self._lastparticle = [name, id]

    def _compare(self, A, B):
        """Compare partiles in list A and B assuming it's the same particles in both lists
        (same length, same names, same ids, same order)

        Add them all to the table and show changes in all properties if any"""
        for a,b in zip(A, B):
            diff = a.diff(b)
            if not diff:
                self._add_row("", a.name, a.id, "", "", "", a.line, b.line)

            for property, (old, new) in diff.items():
                self._add_row('changed', a.name, a.id, property, old, new, a.line, b.line)

    def _added(self, B):
        """Add new particles that got added to the table"""
        for b in B:
            for key, value in zip(b._fields[2:-1], b[2:]):
                self._add_row('added', b.name, b.id, key, "--", value, '--', b.line)

    def _removed(self, A):
        """Show removed particles in the table"""
        for a in A:
            for key, value in zip(a._fields[2:-1], a[2:]):
                self._add_row('removed', a.name, a.id, key, value, '--', a.line, '--')

    def __str__(self):
        """Return string representation of the table"""
        return ET.tostring(self._table, encoding='unicode')

    def _sort_by(self, A, B):
        """
        Sort list B by the contents in A: Make sure the particles that exist in
        A come in the same order and the ones that don't exist at the and
        ordered by line number in B
        """
        Bdict = {b.id: b for b in B}
        B = []
        for a in A:
            b = Bdict.pop(a.id, None)
            if b is not None:
                B.append(b)
        remaining = sorted(Bdict.values(), key=lambda x: x.line)
        B += remaining
        return B

    def fill(self):
        """Fill the table from the contents of the two files given at construction"""
        A = parse_evtpdl(self.fileA)
        B = parse_evtpdl(self.fileB)

        if self.order == 'name':
            A.sort(key=lambda x: x.name)
            B.sort(key=lambda x: x.name)
        elif self.order == 'id':
            A.sort(key=lambda x: x.id)
            B.sort(key=lambda x: x.id)
        elif self.order == 'a':
            B = self._sort_by(A, B)
        elif self.order == 'b':
            A = self._sort_by(B, A)

        # use difflib to get matching blocks of particles so we can easily compare values of A to B
        diff = difflib.SequenceMatcher(a=A, b=B)
        for tag, i1, i2, j1, j2 in diff.get_opcodes():
            if tag == "equal":
                self._compare(A[i1:i2], B[j1:j2])
            if tag in ["delete", "replace"]:
                self._removed(A[i1:i2])
            if tag in ["insert", "replace"]:
                self._added(B[j1:j2])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("fileA", help="Base file for the comparison")
    parser.add_argument("fileB", help="Second file for the comparison")
    parser.add_argument("-s", "--sort", choices=['A', 'B', 'name', 'id'], default="name",
                        help="How to sort the the result.nThe default is to sort "
                        "by particle name but it can be sorted by the order of the "
                        "input file or the particle id as well")
    parser.add_argument("--tolerance", type=float, default=1e-5,
                        help="Relative and absolute comparison "
                        "tolerance for float values, default is 1e-5")
    parser.add_argument("--precision", type=int, default=5,
                        help="Maximum precision for floating point values in the table")
    parser.add_argument("-o", "--output", type=str, default="evtpdl_diff.html",
                        help="Name of the output html file (default: evtpdl_diff.html)")
    parser.add_argument("--open-browser", action="store_true", default=False,
                        help="If given open the result in a webbrowser")
    args = parser.parse_args()

    table = PDLDiffTable(args.fileA, args.fileB, order=args.sort, tolerance=args.tolerance, precision=args.precision)
    table.fill()

    with open(args.output, "w") as html:
        html.write(f"""
<html>
<head>
    <title>Differences between {args.fileA} and {args.fileB}</title>
    <style type="text/css">
    table {{width:80%; border-collapse:collapse;}}
    .removed {{background: rgb(255, 196, 193);}}
    .added {{background: rgb(181, 239, 219);}}
    td {{text-align: right; padding:4px;}}
    td:nth-child(1), td:nth-child(2) {{text-align: center;}}
    tr.newparticle td {{border-top: 1px solid #cccccc;}}
    tr.newparticle .removed {{border-top: 1px solid rgb(255, 137, 131);}}
    tr.newparticle .added {{border-top: 1px solid rgb(107, 223, 184);}}
    </style>
</head>
<body>
<h1>Differences between {args.fileA} and {args.fileB}</h1>
{table}
</body>
</html>
""")

    if args.open_browser:
        import webbrowser
        webbrowser.open(args.output, 0)
