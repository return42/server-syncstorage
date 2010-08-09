# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is Sync Server
#
# The Initial Developer of the Original Code is the Mozilla Foundation.
# Portions created by the Initial Developer are Copyright (C) 2010
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#   Tarek Ziade (tarek@mozilla.com)
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****
"""
SQL backend
"""
from time import time

from sqlalchemy import create_engine
from sqlalchemy.sql import text

from weaveserver.storage import WeaveStorage
from weaveserver.storage.sqlmappers import tables
from weaveserver.util import (time2bigint, bigint2time, round_time,
                              validate_password)
from weaveserver.wbo import WBO

_SQLURI = 'mysql://sync:sync@localhost/sync'
_STANDARD_COLLECTIONS = {1: 'client', 2: 'crypto', 3: 'forms', 4: 'history'}
_STANDARD_COLLECTIONS_NAMES = dict([(value, key) for key, value in
                                    _STANDARD_COLLECTIONS.items()])


class WeaveSQLStorage(object):

    def __init__(self, sqluri=_SQLURI, standard_collections=False):
        self.sqluri = sqluri
        self._engine = create_engine(sqluri, pool_size=20)
        for table in tables:
            table.metadata.bind = self._engine
            table.create(checkfirst=True)
        self._user_collections = {}
        self.engine_name = self._engine.name
        self.standard_collections = standard_collections

    @classmethod
    def get_name(cls):
        """Returns the name of the storage"""
        return 'sql'

    #
    # Users APIs
    #

    def user_exists(self, user_id):
        """Returns true if the user exists."""
        query = text('select id from users where id = :user_id')
        res = self._engine.execute(query, user_id=user_id).fetchone()
        return res is not None

    def set_user(self, user_id, **values):
        """set information for a user. values contains the fields to set.

        If the user doesn't exists, it will be created."""
        values['id'] = user_id
        if not self.user_exists(user_id):
            fields = values.keys()
            params = ','.join([':%s' % field for field in fields])
            fields = ','.join(fields)
            query = text('insert into users (%s) values (%s)' % \
                            (fields, params))
        else:
            fields = values.keys()
            params = ','.join(['%s = :%s' % (field, field)
                               for field in fields])
            query = text('update users set %s where id = :id' \
                         % params)

        self._engine.execute(query, **values)

    def get_user(self, user_id, fields=None):
        """Returns user information.

        If fields is provided, its a list of fields to return
        """
        if fields is None:
            fields = ['*']
        fields = ', '.join(fields)
        query = text('select %s from users where id = :user_id' \
                     % fields)
        return self._engine.execute(query, user_id=user_id).first()

    def delete_user(self, user_id):
        """Removes a user (and all its data)"""
        # removing collections
        query = text('delete from collections where '
                     'userid = :user_id')
        self._engine.execute(query, user_id=user_id)

        # removing items
        query = text('delete from wbo where '
                     'username = :user_id')
        self._engine.execute(query, user_id=user_id)

        # XXX remove reset codes

        # removing user
        query = text('delete from users where id = :user_id')
        return self._engine.execute(query, user_id=user_id)

    def _get_collection_id(self, user_id, collection_name, create=True):
        """Returns a collection id, given the name."""
        if (self.standard_collections and
            collection_name in _STANDARD_COLLECTIONS_NAMES):
            return _STANDARD_COLLECTIONS_NAMES[collection_name]

        # custom collection
        data = self.get_collection(user_id, collection_name,
                                   ['collectionid'])
        if data is None:
            # we want to create it
            if not create:
                return None
            return self.set_collection(user_id, collection_name)

        return data['collectionid']

    def delete_storage(self, user_id):
        """Removes all user data"""
        # removing collections
        query = text('delete from collections where '
                     'userid = :user_id')
        self._engine.execute(query, user_id=user_id)

        # removing items
        query = text('delete from wbo where '
                     'username = :user_id')

        self._engine.execute(query, user_id=user_id)
        # XXX see if we want to check the rowcount
        return True

    #
    # Collections APIs
    #

    def delete_collection(self, user_id, collection_name):
        """deletes a collection"""
        if not self.collection_exists(user_id, collection_name):
            return

        # removing items first
        self.delete_items(user_id, collection_name)
        query = text('delete from collections where '
                     'userid = :user_id and name = :name')

        return self._engine.execute(query, user_id=user_id, name=collection_name)

    def collection_exists(self, user_id, collection_name):
        """Returns True if the collection exists"""
        query = text('select collectionid from collections where '
                     'userid = :user_id and name = :name')
        res = self._engine.execute(query, user_id=user_id,
                                 name=collection_name)
        res = res.fetchone()
        return res is not None

    def set_collection(self, user_id, collection_name, **values):
        """Creates a collection"""
        # XXX values is not used for now because there are no values besides
        # the name
        if self.collection_exists(user_id, collection_name):
            return

        values['userid'] = user_id
        values['name'] = collection_name

        # getting the max collection_id
        # XXX why don't we have an autoinc here ?
        # see https://bugzilla.mozilla.org/show_bug.cgi?id=579096
        max = text('select max(collectionid) from collections where '
                   'userid = :user_id')
        max = self._engine.execute(max, user_id=user_id).first()
        if max[0] is None:
            next_id = 1
        else:
            next_id = max[0] + 1

        # insertion
        values['collectionid'] = next_id
        fields = values.keys()
        params = ','.join([':%s' % field for field in fields])
        fields = ','.join(fields)
        query = text('insert into collections (%s) values (%s)' % \
                        (fields, params))
        self._engine.execute(query, **values)
        return next_id

    def get_collection(self, user_id, collection_name, fields=None):
        """Return information about a collection."""
        if fields is None:
            fields = ['*']
        fields = ', '.join(fields)
        query = text('select %s from collections where '
                     'userid = :user_id and name = :name'\
                     % fields)
        res = self._engine.execute(query, user_id=user_id,
                                   name=collection_name).first()
        # the collection is created
        if res is None:
            collid = self.set_collection(user_id, collection_name)
            res = {'userid': user_id, 'collectionid': collid,
                   'name': collection_name}
            if fields is not None:
                for key in res.keys():
                    if key not in fields:
                        del res[key]
        else:
            # make this a single step
            res = dict([(key, value) for key, value in res.items()
                         if value is not None])
        return res

    def get_collections(self, user_id, fields=None):
        """returns the collections information """
        if fields is None:
            fields = ['*']
        fields = ', '.join(fields)
        query = text('select %s from collections where userid = :user_id'
                     % fields)
        return self._engine.execute(query, user_id=user_id).fetchall()

    def get_collection_names(self, user_id):
        """return the collection names for a given user"""
        query = text('select collectionid, name from collections '
                     'where userid = :user_id')
        return self._engine.execute(query, user_id=user_id).fetchall()

    def get_collection_timestamps(self, user_id):
        """return the collection names for a given user"""
        # XXX doing a call on two tables to get the collection name
        # see if a client-side (eg this code) list of collections
        # makes things faster but I doubt it
        query = text('select name, max(modified) as timestamp '
                     'from wbo, collections where username = :user_id '
                     'group by name')
        res = self._engine.execute(query, user_id=user_id).fetchall()
        return dict([(name, bigint2time(stamp))
                     for name, stamp in res])

    def _collid2name(self, user_id, collection_id):
        if (self.standard_collections and
            collection_id in _STANDARD_COLLECTIONS):
            return _STANDARD_COLLECTIONS[collection_id]

        # custom collections
        if user_id not in self._user_collections:
            names = dict(self.get_collection_names(user_id))
            self._user_collections[user_id] = names

        return self._user_collections[user_id][collection_id]

    def _purge_user_collections(self, user_id):
        if user_id in self._user_collections:
            del self._user_collections[user_id]

    def get_collection_counts(self, user_id):
        """Return the collection counts for a given user"""
        query = text('select collection, count(collection) as ct '
                     'from wbo where username = :user_id '
                     'group by collection')
        try:
            res = [(self._collid2name(user_id, collid), count)
                    for collid, count in
                   self._engine.execute(query, user_id=user_id)]
        finally:
            self._purge_user_collections(user_id)

        return dict(res)

    def get_collection_max_timestamp(self, user_id, collection_name):
        """Returns the max timestamp of a collection."""
        collection_id = self._get_collection_id(user_id, collection_name)
        query = text('select max(modified) '
                     'from wbo where username = :user_id '
                     'and collection = :collection_id')
        res = self._engine.execute(query, user_id=user_id,
                                   collection_id=collection_id)
        res = res.fetchone()
        stamp = res[0]
        if stamp is None:
            return None
        return bigint2time(stamp)


    #
    # Items APIs
    #

    def item_exists(self, user_id, collection_name, item_id):
        """Returns a timestamp if an item exists."""
        collection_id = self._get_collection_id(user_id, collection_name)
        query = text('select modified from wbo where '
                     'username = :user_id and collection = :collection_id '
                     'and id = :item_id')
        res = self._engine.execute(query, user_id=user_id, item_id=item_id,
                                   collection_id=collection_id)
        res = res.fetchone()
        if res is None:
            return None
        return bigint2time(res[0])

    def get_items(self, user_id, collection_name, fields=None, filters=None,
                  limit=None, offset=None, sort=None):
        """returns items from a collection

        "filter" is a dict used to add conditions to the db query.
        Its keys are the field names on which the condition operates.
        Its values are the values the field should have.
        It can be a single value, or a list. For the latter the in()
        operator is used. For single values, the operator has to be provided.
        """
        collection_id = self._get_collection_id(user_id, collection_name)
        if fields is None:
            fields = ['*']
        fields = ', '.join(fields)

        # preparing filters
        extra = []
        extra_values = {}
        if filters is not None:
            for field, value in filters.items():
                operator, value = value
                if field == 'modified':
                    value = time2bigint(value)

                if isinstance(value, (list, tuple)):
                    value = [str(item) for item in value]
                    extra.append('%s %s (%s)' % (field, operator,
                                 ','.join(value)))
                else:
                    #value = str(value)
                    extra.append('%s %s :%s' % (field, operator, field))
                    extra_values[field] = value

        query = ('select %s from wbo where username = :user_id and '
                 'collection = :collection_id' % fields)

        if extra != []:
            query = '%s and %s' % (query, ' and '.join(extra))

        if sort is not None:
            if sort == 'oldest':
                query += " order by modified asc"
            elif sort == 'newest':
                query += " order by modified desc"
            else:
                query += " order by sortindex desc"

        if limit is not None and int(limit) > 0:
            query += ' limit %d' % limit

        if offset is not None and int(offset) > 0:
            query += ' offset %d' % offset

        res = self._engine.execute(text(query), user_id=user_id,
                                   collection_id=collection_id,
                                   **extra_values).fetchall()

        return [WBO(line, {'modified': bigint2time}) for line in res]

    def get_item(self, user_id, collection_name, item_id, fields=None):
        """returns one item"""
        collection_id = self._get_collection_id(user_id, collection_name)
        if fields is None:
            fields = ['*']
        fields = ', '.join(fields)
        query = text('select %s from wbo where '
                     'username = :user_id and collection = :collection_id '
                     'and id = :item_id ' % fields)
        res = self._engine.execute(query, user_id=user_id, item_id=item_id,
                                  collection_id=collection_id).first()
        if res is None:
            return None

        return WBO(res, {'modified': bigint2time})

    def _set_item(self, user_id, collection_name, item_id, **values):
        """Adds or update an item"""
        if 'modified' in values:
            values['modified'] = time2bigint(values['modified'])

        modified = self.item_exists(user_id, collection_name, item_id)

        if modified is None:   # does not exists
            fields = values.keys()
            params = ','.join([':%s' % field for field in fields])
            fields = ','.join(fields)
            query = text('insert into wbo (%s) values (%s)' % \
                            (fields, params))
        else:
            fields = [key for key in values.keys()
                      if key not in ('username', 'collection', 'id')]
            params = ','.join(['%s = :%s' % (field, field)
                               for field in fields if field != ''])
            query = text('update wbo set %s where id = :id and '
                         'username = :username and collection = :collection' \
                         % params)

        self._engine.execute(query, **values)

        if 'modified' in values:
            return bigint2time(values['modified'])

        return modified

    def set_item(self, user_id, collection_name, item_id, **values):
        """Adds or update an item"""
        values['collection'] = self._get_collection_id(user_id,
                                                       collection_name)
        values['id'] = item_id
        values['username'] = user_id
        if 'payload' in values and 'modified' not in values:
            values['modified'] = time()

        return self._set_item(user_id, collection_name, item_id, **values)

    def set_items(self, user_id, collection_name, items):
        """Adds or update a batch of items.

        Returns a list of success or failures.
        """
        if self.engine_name == 'sqlite':
            count = 0
            for item in items:
                if 'id' not in item:
                    continue
                item_id = item['id']
                self.set_item(user_id, collection_name, item_id, **item)
                count += 1
            return count


        fields = ('id', 'parentid', 'predecessorid', 'sortindex', 'modified',
                  'payload', 'payload_size')

        query = 'insert into wbo (username, collection, %s) values ' \
                    % ','.join(fields)

        values = {}
        values['collection'] = self._get_collection_id(user_id,
                                                       collection_name)
        values['user_id'] = user_id

        # building the values batch
        binds = [':%s%%(num)d' % field for field in fields]
        pattern = '(:user_id,:collection,%s) ' % ','.join(binds)

        lines = []
        for num, item in enumerate(items):
            lines.append(pattern % {'num': num})
            for field in fields:
                value = item.get(field)
                if field == 'modified':
                    value = time2bigint(value)
                values['%s%d' % (field, num)] = value

            if ('payload%d' % num in values and
                'modified%d' % num not in values):
                values['modified%d' % num] = time2bigint(time())

        query += ','.join(lines)

        # allowing updates as well
        query += (' on duplicate key update parentid = values(parentid),'
                  'predecessorid = values(predecessorid),'
                  'sortindex = values(sortindex),'
                  'modified = values(modified), payload = values(payload),'
                  'payload_size = values(payload_size)')

        res = self._engine.execute(text(query), **values)
        return res.rowcount

    def delete_item(self, user_id, collection_name, item_id):
        """Deletes an item"""
        collection_id = self._get_collection_id(user_id, collection_name)
        query = text('delete from wbo where username = :user_id and '
                     'collection = :collection_id and id = :item_id')
        res = self._engine.execute(query, user_id=user_id,
                                 collection_id=collection_id, item_id=item_id)
        return res.rowcount == 1

    def delete_items(self, user_id, collection_name, item_ids=None,
                     filters=None, limit=None, offset=None, sort=None):
        """Deletes items. All items are removed unless item_ids is provided"""
        collection_id = self._get_collection_id(user_id, collection_name)

        if item_ids is None:
            query = ('delete from wbo where username = :user_id and '
                     'collection = :collection_id')
        else:
            ids = ', '.join([str(id_) for id_ in item_ids])
            query = ('delete from wbo where username = :user_id and '
                     'collection = :collection_id and id in (%s)' % ids)

        # preparing filters
        extra = []
        extra_values = {}
        if filters is not None:
            for field, value in filters.items():
                operator, value = value
                if field == 'modified':
                    value = time2bigint(value)

                if isinstance(value, (list, tuple)):
                    value = [str(item) for item in value]
                    extra.append('%s %s (%s)' % (field, operator,
                                 ','.join(value)))
                else:
                    #value = str(value)
                    extra.append('%s %s :%s' % (field, operator, field))
                    extra_values[field] = value

        if extra != []:
            query = '%s and %s' % (query, ' and '.join(extra))


        if sort is not None and self.engine_name != 'sqlite':
            if sort == 'oldest':
                query += " order by modified"
            elif sort == 'newest':
                query += " order by modified desc"
            elif sort == 'index':
                query += " order by sortindex desc"

        if self.engine_name != 'sqlite':
            if limit is not None and int(limit) > 0:
                query += ' limit %d' % limit

            if offset is not None and int(offset) > 0:
                query += ' offset %d' % offset

        # XXX see if we want to send back more details
        # e.g. by checking the rowcount
        res = self._engine.execute(text(query), user_id=user_id,
                                 collection_id=collection_id, **extra_values)
        return res.rowcount > 0


WeaveStorage.register(WeaveSQLStorage)