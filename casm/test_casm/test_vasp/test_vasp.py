"""test_casm/test_vasp/test_vasp.py"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)
from builtins import *

import unittest
import os
from os.path import join
import json

from casm import vasp
from casm.misc.contexts import working_dir, captured_output, print_stringIO
from casm.vasp.io import Poscar

import test_casm
from test_casm.test_vasp import CasmVaspTestCase, cp_input


class TestCasmVasp(CasmVaspTestCase):
    def setUp(self):
        """Read test case data"""
        with open(join(self.classdir, 'test_cases.json'), 'r') as f:
            self.cases = json.load(f)["vasp"]

    def test_run(self):
        """Test vasp.run()"""
        for i, case in enumerate(self.cases["run"]):
            input = join(self.classdir, 'input_data', case['input_data'])
            output = join(self.classdir, 'output_data', 'vasp', 'run',
                          'test_case_' + str(i))
            cp_input(input, output)
            with captured_output() as (sout, serr):
                if self.has_vasp:
                    vasp.run(output, **case["settings"])
                    self.assertTrue(True)  # Todo: add tests
                else:
                    self.assertRaisesRegexp(OSError,
                                            "No such file or directory",
                                            vasp.run, output,
                                            **case["settings"])
            #print_stringIO(sout) # print stdout from captured_output context
            #print_stringIO(serr) # print stderr from captured_output context


class TestCasmVaspReadStructureFromConfigJson(CasmVaspTestCase):
    def setUp(self):
        """Read test case data"""
        with open(join(self.classdir, 'test_cases.json'), 'r') as f:
            self.cases = json.load(
                f)['vasp']['read_structure_from_structure_json']

    def test_run(self):
        """Test read_structure_json function"""
        for i, case in enumerate(self.cases[1:]):
            test_poscar = Poscar(
                join(self.classdir, 'input_data', case['input_data'],
                     'structure.json'))
            self.assertTrue(test_poscar.lattice().tolist() == case['lattice'])
            self.assertTrue(test_poscar.coord_mode == 'Cartesian')
            self.assertTrue(test_poscar.scaling == 1.0)
            self.assertTrue(test_poscar.type_atoms == case['type_atoms'])
            self.assertTrue(test_poscar.num_atoms == case['num_atoms'])
            for j, site in enumerate(test_poscar.basis):
                self.assertTrue(
                    site.position.tolist() == case['atom_coords'][j])
