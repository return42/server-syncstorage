# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
""" BSO object -- used for (de)serialization
"""

import re
import json
import decimal
import six

FIELDS = set(('id', 'collection', 'sortindex', 'modified',
              'payload', 'payload_size', 'ttl'))

FIELD_DEFAULTS = {
    "payload": "",
    "sortindex": None,
    "ttl": None,
}

MAX_TTL = 31536000
MAX_PAYLOAD_SIZE = 256 * 1024
MAX_SORTINDEX_VALUE = 999999999
MIN_SORTINDEX_VALUE = -999999999
VALID_ID_REGEX = re.compile("^[ -~]{1,64}$")  # <=64 printable characters

SCALAR_TYPES = six.integer_types + six.string_types + (decimal.Decimal, )


class BSO(dict):
    """Holds BSO info"""

    def __init__(self, data=None, converters=None):
        super(BSO, self).__init__()
        if data is None:
            data = {}
        if converters is None:
            converters = {}

        try:
            data_items = data.items()
        except AttributeError:
            msg = "BSO data must be dict-like, not %s"
            raise ValueError(msg % (type(data),))

        for name, value in data_items:
            if value is not None:
                if not isinstance(value, SCALAR_TYPES):
                    msg = "BSO fields must be scalar values, not %s"
                    raise ValueError(msg % (type(value),))
            if name in converters:
                value = converters[name](value)
            if value is None:
                continue

            self[name] = value

    def __str__(self):
        fields = dict((k, v) for (k, v) in self.items() if k != 'payload')
        return "BSO(%s)" % (json.dumps(fields, sort_keys=True),)

    def validate(self):
        """Validates the values the BSO has."""
        # pylint: disable=R0911,R0912
        # Check that there are no extraneous fields.
        for name in self:
            if name not in FIELDS:
                return False, 'unknown field %r' % (name,)

        # Check that id field is well-formed.
        if 'id' in self:
            value = self['id']
            # Check that it's printable-asscii characters.
            # Doing the regex match first has the nice side-effect of
            # erroring out if the value is not a string or unicode object.
            # This avoids accidentally coercing other types to a string.
            try:
                if not VALID_ID_REGEX.match(value):
                    return False, 'invalid id'
                # A regex like /^[blah]$/ can happily match a string
                # with a trailing newline because of how the '$' is
                # interpreted.  Guard against it explicitly.
                if value[-1] == '\n':
                    return False, 'invalid id'
            except TypeError:
                return False, 'invalid id'
            # Make sure it's stored as a bytestring, not a unicode object.
            # This won't fail because we've checked for valid chars above.
            value = str(self['id'])
            self['id'] = value

        # Check that the ttl is a positive int, and less than one year.
        if 'ttl' in self:
            try:
                ttl = int(self['ttl'])
            except ValueError:
                return False, 'invalid ttl'
            if ttl < 0:
                return False, 'invalid ttl'
            self['ttl'] = ttl
            # XXX TODO: temporary workaround for clients that accidentally
            # cached a server-side ttl value and are now sending it in
            # future updates. Since it's invalid, we assume they didn't
            # actually mean to send one at all.
            # See https://bugzilla.mozilla.org/show_bug.cgi?id=977397
            if ttl > MAX_TTL:
                del self['ttl']

        # Check that the sortindex is a valid positive integer.
        # Convert from other types as necessary.
        if 'sortindex' in self:
            try:
                self['sortindex'] = int(self['sortindex'])
            except ValueError:
                return False, 'invalid sortindex'
            if self['sortindex'] > MAX_SORTINDEX_VALUE:
                return False, 'invalid sortindex'
            if self['sortindex'] < MIN_SORTINDEX_VALUE:
                return False, 'invalid sortindex'

        # Check that the payload is a string, and is not too big.
        payload = self.get('payload')
        if payload is not None:
            if not isinstance(payload, six.string_types):
                return False, 'payload not a string'
            self['payload_size'] = len(payload.encode("utf8"))
            if self['payload_size'] > MAX_PAYLOAD_SIZE:
                return False, 'payload too large'

        return True, None
