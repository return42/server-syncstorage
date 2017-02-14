# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import mozsvc.config

__version__      = "2.0.0rc1"
__description__  = "Storage Engine for Firefox Sync Server, version 1.5"
__url__          = "https://github.com/mozilla-services/syncstorage"
__license__      = "MPLv2.0"
__author__       = 'Mozilla Services'
__author_email__ = 'services-dev@mozilla.org'
__keywords__     = 'mozilla cloud syncstorage'


def includeme(config):
    """Install SyncStorage application into the given Pyramid configurator."""
    # Disable cornice default exception-handling views.
    config.registry.settings.setdefault("handle_exceptions", False)
    # Include dependencies from other packages.
    config.include("cornice")
    config.include("mozsvc")
    config.include("mozsvc.user")
    # Add in the stuff we define ourselves.
    config.include("syncstorage.tweens")
    config.include("syncstorage.storage")
    config.include("syncstorage.views")


def get_configurator(global_config, **settings):
    """Load a SyncStorge configurator object from deployment settings."""
    config = mozsvc.config.get_configurator(global_config, **settings)
    config.begin()
    try:
        config.include(includeme)
    finally:
        config.end()
    return config


def main(global_config, **settings):
    """Load a SyncStorage WSGI app from deployment settings."""
    config = get_configurator(global_config, **settings)
    return config.make_wsgi_app()
