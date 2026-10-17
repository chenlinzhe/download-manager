# -*- coding: utf-8 -*-
"""下载包管家 - server 纯逻辑单元测试（stdlib unittest，无需额外依赖）。
运行：python -m unittest discover -s tests -v
"""
import io, json, os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server


class TempApp(unittest.TestCase):
    """把持久化文件指到临时目录，避免污染真实配置。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self._saved = {}
        for name in ('SETTINGS_FILE', 'LABELS_FILE', 'SNAPSHOT_FILE', 'INVENTORY_FILE',
                     'AI_CACHE_FILE', 'COLLECTION_CACHE_FILE', 'COLLECTION_FAIL_FILE',
                     'MANUAL_ROOTS_FILE'):
            self._saved[name] = getattr(server, name)
            setattr(server, name, self.dir / (name.lower() + '.json'))
        self._roots = server.roots
        server.roots = lambda: []

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(server, name, value)
        server.roots = self._roots
        self.tmp.cleanup()


class TestBasics(unittest.TestCase):
    def test_download_dir(self):
        self.assertTrue(server.download_dir('Downloads'))
        self.assertTrue(server.download_dir('D:\\迅雷下载'))
        self.assertFalse(server.download_dir('工作文档'))

    def test_media_file_kind(self):
        self.assertEqual(server.media_file_kind(Path('a.jpg')), '图片')
        self.assertEqual(server.media_file_kind(Path('a.mp4')), '视频')
        self.assertEqual(server.media_file_kind(Path('a.mp3')), '音乐')
        self.assertEqual(server.media_file_kind(Path('a.zip')), '')

    def test_fingerprint_is_stable(self):
        item = {'name': 'Foo.zip', 'size': 10, 'modified': '2026-01-01T00:00:00'}
        self.assertEqual(server.item_fingerprint(item), 'foo.zip|10|2026-01-01T00:00:00')

    def test_split_query_terms(self):
        terms = server.split_query_terms('找那个装 CUDA 的安装包')
        self.assertIn('cuda', terms)


class TestAnalyze(TempApp):
    def test_empty_dir_is_dropped(self):
        p = self.dir / 'empty'
        p.mkdir()
        out = server.analyze(p, 0, 0, p.stat().st_mtime, [])
        self.assertEqual(out['recommendation'], '不用保住')
        self.assertLess(out['score'], 5)

    def test_crack_hint_lowers_score(self):
        p = self.dir / 'navicat.rar'
        p.write_bytes(b'x')
        clean = server.analyze(p, 10, 1, p.stat().st_mtime, [])
        risky = server.analyze(p, 10, 1, p.stat().st_mtime, ['keygen.exe'])
        self.assertLess(risky['score'], clean['score'])
        self.assertTrue(risky['suspicious'])

    def test_media_dir_kept(self):
        p = self.dir / 'photos'
        p.mkdir()
        self.assertEqual(server.media_directory_kind(p) in ('', '图片'), True)


class TestAllowed(TempApp):
    def test_depth_rule(self):
        root = self.dir / '下载'
        (root / 'pkg').mkdir(parents=True)
        (root / 'coll' / 'member').mkdir(parents=True)
        (root / 'a' / 'b' / 'c').mkdir(parents=True)
        server.roots = lambda: [root]
        self.assertTrue(server.allowed(root / 'pkg'))
        self.assertTrue(server.allowed(root / 'coll' / 'member'))
        self.assertFalse(server.allowed(root / 'a' / 'b' / 'c'))
        self.assertFalse(server.allowed(self.dir))


class TestKeep(TempApp):
    def test_returns_only_newly_marked(self):
        root = self.dir / '下载'
        (root / 'one').mkdir(parents=True)
        (root / 'two').mkdir(parents=True)
        server.roots = lambda: [root]
        first = server.save_keep([str(root / 'one')])
        self.assertEqual(len(first), 1)
        second = server.save_keep([str(root / 'one'), str(root / 'two')])
        self.assertEqual(len(second), 2, '本次标记 2 项应返回 2 项，而非历史累计')
        labels = server.load_labels()
        self.assertEqual(len(labels), 2)


class TestMove(TempApp):
    def test_partial_failure_reported(self):
        root = self.dir / '下载'
        for name in ('a', 'b'):
            (root / name).mkdir(parents=True)
            (root / name / 'f.txt').write_text('x', encoding='utf-8')
        dest = self.dir / '归档'
        server.roots = lambda: [root]
        # 预先占用其中一个目标名，模拟冲突
        (dest).mkdir()
        (dest / 'b').mkdir()
        out = server.move([str(root / 'a'), str(root / 'b')], str(dest))
        self.assertEqual(len(out['done']), 1)
        self.assertEqual(len(out['failed']), 1)
        self.assertIn('目标已存在', out['failed'][0]['error'])
        self.assertTrue((dest / 'a' / 'f.txt').exists())

    def test_relative_dest_rejected(self):
        with self.assertRaises(ValueError):
            server.move([], 'relative/dir')


class TestSettings(TempApp):
    def test_api_key_encrypted_and_clearable(self):
        server.save_settings({'apiKey': 'sk-test-1234', 'autoSearch': False})
        raw = json.loads(server.SETTINGS_FILE.read_text(encoding='utf-8'))
        self.assertNotIn('apiKey', raw, '明文 Key 不应落盘')
        self.assertTrue(raw.get('apiKeyEnc'))
        self.assertEqual(server.get_settings(True)['apiKey'], 'sk-test-1234')
        self.assertEqual(server.get_settings(False)['apiKeyMasked'][-4:], '1234')

        server.save_settings({'clearApiKey': True})
        self.assertEqual(server.get_settings(True)['apiKey'], '')
        self.assertFalse(server.get_settings(False)['apiKeyMasked'])
        self.assertFalse(server.get_settings(True)['autoSearch'], '清除 Key 不应把 autoSearch 打回 True')

    def test_destination_persisted(self):
        server.save_settings({'destination': 'F:\\归档'})
        self.assertEqual(server.get_settings(True)['destination'], 'F:\\归档')

    def test_dpapi_roundtrip(self):
        token = server.protect_key('sk-roundtrip')
        self.assertTrue(token)
        self.assertEqual(server.unprotect_key(token), 'sk-roundtrip')
        self.assertEqual(server.unprotect_key('not-hex'), '')


class TestCollectionPrejudge(TempApp):
    def test_multiple_installers_is_collection(self):
        p = self.dir / '软件合集'
        p.mkdir()
        for name in ('a.zip', 'b.rar', 'c.exe'):
            (p / name).write_bytes(b'x')
        hint = server.collection_prejudge(p)
        self.assertTrue(hint and hint['isCollection'])

    def test_install_dir_is_not_collection(self):
        p = self.dir / 'App'
        p.mkdir()
        (p / 'app.exe').write_bytes(b'x')
        (p / 'core.dll').write_bytes(b'x')
        hint = server.collection_prejudge(p)
        self.assertFalse(hint['isCollection'])

    def test_single_child_not_collection(self):
        p = self.dir / 'solo'
        p.mkdir()
        (p / 'readme.txt').write_text('x', encoding='utf-8')
        self.assertFalse(server.collection_prejudge(p)['isCollection'])

    def test_unknown_returns_none(self):
        p = self.dir / 'mixed'
        p.mkdir()
        (p / 'one.txt').write_text('x', encoding='utf-8')
        (p / 'two.txt').write_text('x', encoding='utf-8')
        self.assertIsNone(server.collection_prejudge(p))


if __name__ == '__main__':
    unittest.main()
