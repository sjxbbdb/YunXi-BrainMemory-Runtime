"""Environment compatibility for YunXi-BrainMemory-Runtime."""

import os
import unittest
import warnings
from unittest import mock
from pathlib import Path

import config
from tools import p7_controlled_host as p7


class EnvCompatTests(unittest.TestCase):
    def setUp(self):
        self.environment = mock.patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        with config._env_warning_lock:
            previous = config._warned_legacy_names.copy()
            config._warned_legacy_names.clear()
        self.addCleanup(self.restore_warned, previous)

    @staticmethod
    def restore_warned(previous):
        with config._env_warning_lock:
            config._warned_legacy_names.clear()
            config._warned_legacy_names.update(previous)

    def test_new_name_wins_including_empty(self):
        os.environ['BRAIN_MEMORY_OFFLINE'] = '1'
        for value in ('0', ''):
            with self.subTest(value=value):
                os.environ['YUNXI_BRAIN_OFFLINE'] = value
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter('always')
                    self.assertEqual(config.env_get('OFFLINE'), value)
                self.assertEqual(caught, [])
        self.assertEqual(config._warned_legacy_names, set())

    def test_legacy_fallback_warns_once_per_name(self):
        os.environ.update(BRAIN_MEMORY_OFFLINE='1', BRAIN_MEMORY_HOST='localhost')
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            with self.assertLogs('yunxi-brainmemory.config', level='WARNING') as logs:
                for _ in range(3):
                    self.assertEqual(config.env_get('OFFLINE'), '1')
                    self.assertEqual(config.env_get('HOST'), 'localhost')
        self.assertEqual(len(caught), 2)
        self.assertEqual(len(logs.output), 2)
        for suffix, warning in zip(('OFFLINE', 'HOST'), caught):
            self.assertIs(warning.category, DeprecationWarning)
            self.assertIn('BRAIN_MEMORY_' + suffix, str(warning.message))
            self.assertIn(config.env_name(suffix), str(warning.message))
            self.assertTrue(any('BRAIN_MEMORY_' + suffix in line for line in logs.output))

    def test_absent_uses_default(self):
        self.assertIsNone(config.env_get('OFFLINE'))
        self.assertEqual(config.env_get('OFFLINE', 'fallback'), 'fallback')
        self.assertEqual(config.env_name('HOST'), 'YUNXI_BRAIN_HOST')

    def test_typed_helpers_use_compatibility(self):
        os.environ.update(BRAIN_MEMORY_PORT='1234', BRAIN_MEMORY_AUTONOMY_ENABLED='yes')
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', DeprecationWarning)
            self.assertEqual(config._env_int('PORT', 8001, minimum=1, maximum=65535), 1234)
            self.assertTrue(config._env_bool('AUTONOMY_ENABLED', False))
        os.environ.update(YUNXI_BRAIN_PORT='invalid', YUNXI_BRAIN_AUTONOMY_ENABLED='')
        self.assertEqual(config._env_int('PORT', 8001), 8001)
        self.assertFalse(config._env_bool('AUTONOMY_ENABLED', True))
        os.environ['YUNXI_BRAIN_PORT'] = '0'
        self.assertEqual(config._env_int('PORT', 8001, minimum=1), 8001)
        os.environ['YUNXI_BRAIN_PORT'] = '65536'
        self.assertEqual(config._env_int('PORT', 8001, maximum=65535), 8001)

    def test_p7_manifest_key_fallback_and_precedence(self):
        os.environ[p7.LEGACY_MANIFEST_KEY_ENV] = 'legacy-secret-at-least-16-bytes'
        with self.assertWarns(DeprecationWarning):
            legacy_host = p7.P7ControlledHost()
        self.assertTrue(legacy_host._manifest_key_persistent)
        self.assertEqual(legacy_host._manifest_master_key, b'legacy-secret-at-least-16-bytes')
        os.environ[p7.MANIFEST_KEY_ENV] = 'preferred-secret-at-least-16-bytes'
        self.assertEqual(p7.P7ControlledHost()._manifest_master_key, b'preferred-secret-at-least-16-bytes')

    def test_p7_forces_both_offline_names(self):
        os.environ['YUNXI_BRAIN_OFFLINE'] = '0'
        environment = p7._safe_child_environment(root=Path.cwd())
        self.assertEqual(environment['YUNXI_BRAIN_OFFLINE'], '1')
        self.assertEqual(environment['BRAIN_MEMORY_OFFLINE'], '1')
