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
""" SQL Authentication

Users are stored with digest password (sha1)

XXX cost of server-side sha1
XXX cache sha1 + sql
"""
from hashlib import sha1

from sqlalchemy.ext.declarative import declarative_base, Column
from sqlalchemy import Integer, String, create_engine
from sqlalchemy.sql import text

from weave.server.auth import WeaveAuthBase, register

_SQLURI = 'mysql://sync:sync@localhost/sync'
_Base = declarative_base()


class User(_Base):
    """Holds username/sha1-ed password
    """
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(32), nullable=False)
    password = Column(Integer(40), nullable=False)


users = User.__table__


class SQLAuth(WeaveAuthBase):
    """SQL authentication."""

    def __init__(self, sqluri=_SQLURI):
        self._engine = create_engine(sqluri, pool_size=20)
        users.metadata.bind = self._engine
        users.create(checkfirst=True)

    @classmethod
    def get_name(self):
        """Returns the name of the authentication backend"""
        return 'sql'

    def authenticate_user(self, username, password):
        """Authenticates a user given a username and password.

        Returns the user id in case of success. Returns None otherwise."""
        query = ('select id, password from user '
                 'where username = :username')

        user = self._engine.execute(text(query), username=username).fetchone()
        if user is None:
            return None

        sha1_password = sha1(password).hexdigest()
        if user.password == sha1_password:
            return user.id


register(SQLAuth)