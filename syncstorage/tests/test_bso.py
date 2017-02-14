# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# pylint: disable=C0103

import unittest2

from syncstorage.bso import BSO


class TestBSO(unittest2.TestCase):

    def test_test_nonscalar_values_are_rejected(self):
        self.assertRaises(ValueError,
                          BSO, {'payload': ('non', 'scalar', 'value')})

    def test_validation(self):
        bso = BSO()
        result, failure = bso.validate()
        self.assertTrue(result)

        data = {'id': 'bigid' * 30}
        bso = BSO(data)
        result, failure = bso.validate()
        self.assertFalse(result)

        data = {'id': u'I AM A \N{SNOWMAN}'}
        bso = BSO(data)
        result, failure = bso.validate()
        self.assertFalse(result)

        data = {'sortindex': 9999999999}
        bso = BSO(data)
        result, failure = bso.validate()
        self.assertFalse(result)

        data = {'sortindex': '9999'}
        bso = BSO(data)
        result, failure = bso.validate()
        self.assertTrue(result)
        self.assertTrue(bso['sortindex'], 9999)

        data = {'sortindex': 'ok'}
        bso = BSO(data)
        result, failure = bso.validate()
        self.assertFalse(result)

        data = {'sortindex': '12'}
        bso = BSO(data)
        result, failure = bso.validate()
        self.assertTrue(result)
        self.assertEquals(bso['sortindex'], 12)

        for bad_ttl in ('bouh', -1, 31537000):
            data = {'ttl': bad_ttl}
            bso = BSO(data)
            result, failure = bso.validate()
            # XXX TODO: ttls that are too large are currently ignored.
            # See https://bugzilla.mozilla.org/show_bug.cgi?id=977397
            # self.assertFalse(result)
            if bad_ttl != 31537000:
                self.assertFalse(result)
            else:
                self.assertTrue(result)
                self.assertTrue('ttl' not in bso)

        data = {'ttl': 3600}
        bso = BSO(data)
        result, failure = bso.validate()
        self.assertTrue(result)

        data = {'payload': "X" * 30000}
        bso = BSO(data)
        result, failure = bso.validate()
        self.assertTrue(result)

        data = {'payload': "X" * 300000}
        bso = BSO(data)
        result, failure = bso.validate()
        self.assertFalse(result)

        data = {"boooo": ""}
        bso = BSO(data)
        result, failure = bso.validate()
        self.assertFalse(result)

        data = {42: 17}
        bso = BSO(data)
        result, failure = bso.validate()
        self.assertFalse(result)
