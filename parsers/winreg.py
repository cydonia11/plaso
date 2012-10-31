#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright 2012 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""This file contains a Windows registry parser in plaso."""
import logging

from plaso.lib import errors
from plaso.lib import parser
from plaso.lib import win_registry
from plaso.lib import win_registry_interface


class RegistryParser(parser.PlasoParser):
  """A Windows Registry assistance parser for Plaso."""

  # List of types registry types and required keys to identify each of these
  # types.
  REG_TYPES = {
      'NTUSER': ('\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer',),
      'SOFTWARE': ('\\Microsoft\\Windows\\CurrentVersion\\App Paths',),
      'SECURITY': ('\\Policy\\PolAdtEv',),
      'SYSTEM': ('\\Select',),
      'SAM': ('\\SAM\\Domains\\Account\\Users',)
  }

  # Description of the log file.
  NAME = 'Registry Parsing'
  PARSER_TYPE = 'reg'

  def __init__(self, pre_obj):
    super(RegistryParser, self).__init__(pre_obj)
    self._plugins = win_registry_interface.GetRegistryPlugins()

  def Parse(self, filehandle):
    """Return a generator for events extracted from registry files."""
    # TODO: Remove this magic reads when the classifier has been
    # implemented, until then we need to make sure we are dealing with
    # a registry file before proceeding.
    magic = 'regf'
    data = filehandle.read(len(magic))

    codepage = getattr(self._pre_obj, 'codepage', 'cp1252')

    if data != magic:
      raise errors.UnableToParseFile('File %s not a %s. (wrong magic)' % (
          filehandle.name, self.NAME))

    # Determine type, find all parsers
    try:
      reg = win_registry.WinRegistry(filehandle, codepage)
    except IOError as e:
      raise errors.UnableToParseFile(
          '[%s] Unable to parse file %s: %s' % (self.NAME, filehandle.name, e))

    # Detect registry type.
    registry_type = 'all'
    for reg_type in self.REG_TYPES:
      found = True
      for key in self.REG_TYPES[reg_type]:
        if not key in reg:
          found = False
          break
      if found:
        registry_type = reg_type
        break

    self._registry_type = registry_type
    logging.debug('Registry file %s detected as <%s>', filehandle.name,
                  registry_type)

    plugins = {}
    counter = 0
    for weight in self._plugins.GetWeights():
      plist = self._plugins.GetWeightPlugins(weight, registry_type)
      plugins[weight] = []
      for plugin in plist:
        plugins[weight].append(plugin(reg))
        counter += 1

    logging.debug('Number of plugins for this registry file: %d', counter)
    # Recurse through keys and apply action.
    # Order:
    #   Compare against key centric plugins for this type of registry.
    #   Compare against key centric plugin that works against any registry.
    #   Compare against value centric plugins for this type of registry.
    #   Compare against value centric plugins that works against any registry.
    for key in reg:
      parsed = False
      for weight in plugins:
        if parsed:
          break
        for plugin in plugins[weight]:
          call_back = plugin.Process(key)
          if call_back:
            parsed = True
            for evt in self.GetEvents(call_back, key):
              yield evt
            break

  def GetEvents(self, call_back, key):
    """Return all events generated by a registry plugin."""
    for evt in call_back:
      evt.offset = getattr(evt, 'offset', key.offset)
      evt.source_long = getattr(evt, 'source_long',
                                '%s key' % self._registry_type)
      if hasattr(evt, 'source_append'):
        evt.source_long += '%s' % evt.source_append
      if getattr(call_back, 'URLS', None):
        evt.url = ' - '.join(call_back.URLS)
      yield evt

