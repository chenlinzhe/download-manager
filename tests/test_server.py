# -*- coding: utf-8 -*-
"""下载包管家 - server 纯逻辑单元测试（stdlib unittest，无需额外依赖）。
运行：python -m unittest discover -s tests -v
"""
import io, json, os, sys, tempfile, unittest, urllib.error, urllib.request
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
                     'MANUAL_ROOTS_FILE', 'NOTES_FILE', 'IGNORE_FILE'):
            self._saved[name] = getattr(server, name)
            setattr(server, name, self.dir / (name.lower() + '.json'))
        self._roots = server.roots
        server.roots = lambda: []

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(server, name, value)
        server.roots = self._roots
        self.tmp.cleanup()


class FakeEnv(object):
    """拦截环境变量写入，避免测试污染真实的用户环境变量。"""

    def __init__(self):
        self.stored = {}
        self.fail = False
        self.calls = []

    def __call__(self, value):
        self.calls.append(value)
        if self.fail:
            return False
        val = str(value or '').strip()
        if val:
            self.stored[server.ENV_KEY_NAME] = val
        else:
            self.stored.pop(server.ENV_KEY_NAME, None)
        return True


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
    """API Key 只存本机环境变量：配置文件里不留 Key，也不会进 Git。"""

    def setUp(self):
        super().setUp()
        self.env = FakeEnv()
        self._set_env = server.set_user_env_key
        self._env_key = server.env_api_key
        server.set_user_env_key = self.env
        server.env_api_key = lambda: self.env.stored.get(server.ENV_KEY_NAME, '')

    def tearDown(self):
        server.set_user_env_key = self._set_env
        server.env_api_key = self._env_key
        super().tearDown()

    def _raw(self):
        return json.loads(server.SETTINGS_FILE.read_text(encoding='utf-8'))

    def test_key_goes_to_env_not_to_file(self):
        out = server.save_settings({'apiKey': 'sk-' + 'a' * 32, 'autoSearch': False})
        self.assertEqual(out['keyStoredIn'], 'env')
        self.assertEqual(self.env.stored[server.ENV_KEY_NAME], 'sk-' + 'a' * 32)
        raw = self._raw()
        self.assertNotIn('apiKey', raw, '明文 Key 不应落盘')
        self.assertNotIn('apiKeyEnc', raw, 'Key 不该写进配置文件')
        self.assertEqual(server.get_settings(False)['keySource'], 'env')
        self.assertEqual(server.get_settings(False)['apiKeyMasked'][-4:], 'aaaa')

    def test_env_write_failure_falls_back_to_encrypted_file(self):
        self.env.fail = True
        out = server.save_settings({'apiKey': 'sk-' + 'b' * 32})
        self.assertEqual(out['keyStoredIn'], 'file')
        raw = self._raw()
        self.assertNotIn('apiKey', raw)
        self.assertTrue(raw.get('apiKeyEnc'))
        self.assertEqual(server.get_settings(True)['apiKey'], 'sk-' + 'b' * 32)

    def test_clear_key_removes_env_and_file(self):
        server.save_settings({'apiKey': 'sk-' + 'c' * 32, 'autoSearch': False})
        server.save_settings({'clearApiKey': True})
        self.assertEqual(server.get_settings(True)['apiKey'], '')
        self.assertFalse(server.get_settings(False)['apiKeyMasked'])
        self.assertNotIn('apiKeyEnc', self._raw())
        self.assertFalse(server.get_settings(True)['autoSearch'], '清除 Key 不应把 autoSearch 打回 True')

    def test_env_key_wins_over_file(self):
        server.SETTINGS_FILE.write_text(json.dumps({'apiKeyEnc': server.protect_key('sk-file')}), encoding='utf-8')
        self.env.stored[server.ENV_KEY_NAME] = 'sk-env'
        self.assertEqual(server.get_settings(True)['apiKey'], 'sk-env')
        self.assertEqual(server.get_settings(False)['keySource'], 'env')

    def test_legacy_file_key_migrates_to_env_on_save(self):
        server.SETTINGS_FILE.write_text(json.dumps({'apiKey': 'sk-legacy'}), encoding='utf-8')
        out = server.save_settings({'autoSearch': True})
        self.assertEqual(out['keyStoredIn'], 'env')
        self.assertEqual(self.env.stored[server.ENV_KEY_NAME], 'sk-legacy')
        self.assertNotIn('apiKey', self._raw())

    def test_default_model_exists_in_catalog(self):
        self.assertEqual(server.get_settings(False)['model'], 'deepseek-flash')

    def test_legacy_model_name_is_corrected(self):
        server.SETTINGS_FILE.write_text(json.dumps({'model': 'deepseek-v4-flash'}), encoding='utf-8')
        self.assertEqual(server.get_settings(False)['model'], 'deepseek-flash')

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


class TestLlmError(unittest.TestCase):
    """AI 调用失败时要给出中文可读原因，而不是裸 HTTP 错误。"""

    def _http_error(self, code, payload=None):
        body = json.dumps(payload or {'error': {'message': 'boom'}}).encode('utf-8')
        return urllib.error.HTTPError('https://api.deepseek.com', code, 'err', {}, io.BytesIO(body))

    def test_401_mentions_api_key_and_settings(self):
        msg = server._llm_error(self._http_error(401))
        self.assertIn('API Key', msg)
        self.assertIn('模型设置', msg)
        self.assertIn('401', msg)

    def test_402_mentions_balance(self):
        self.assertIn('余额', server._llm_error(self._http_error(402)))

    def test_429_mentions_rate_limit(self):
        self.assertIn('限流', server._llm_error(self._http_error(429)))

    def test_500_mentions_code(self):
        self.assertIn('HTTP 503', server._llm_error(self._http_error(503)))

    def test_url_error_mentions_network(self):
        msg = server._llm_error(urllib.error.URLError('timed out'))
        self.assertIn('连不上', msg)


class TestNotes(TempApp):
    """备注：点击 AI 说明那一格写的文字要能存下来并参与搜索。"""

    def test_save_and_reload(self):
        path = 'D:\\Downloads\\tool.zip'
        r = server.save_note(path, u'  给小李用  \n 别删 ')
        self.assertEqual(r['note'], u'给小李用 别删')
        self.assertEqual(server.load_notes()[path], u'给小李用 别删')

    def test_empty_note_removes(self):
        path = 'D:\\Downloads\\tool.zip'
        server.save_note(path, u'临时')
        server.save_note(path, u'   ')
        self.assertNotIn(path, server.load_notes())

    def test_length_capped(self):
        self.assertEqual(len(server.save_note('p', u'长' * 500)['note']), 200)

    def test_missing_path_rejected(self):
        with self.assertRaises(ValueError):
            server.save_note('', u'x')

    def test_note_merged_into_items(self):
        server.save_note('D:\\Downloads\\a.zip', u'装机必备')
        data = {'items': [{'path': 'D:\\Downloads\\a.zip'}, {'path': 'D:\\Downloads\\b.zip'}]}
        merged = server._with_notes(data)
        self.assertEqual(merged['items'][0]['note'], u'装机必备')
        self.assertEqual(merged['items'][1]['note'], '')

    def test_note_used_by_search_text(self):
        item = server._search_text({'name': 'x.zip', 'note': u'装机必备'})
        self.assertIn(u'装机必备', item)


class TestKeyFormat(unittest.TestCase):
    """Key 格式能自查，401 时能指认具体是哪把 Key。"""

    def test_valid_key_has_no_problem(self):
        self.assertEqual(server.key_format_problem('sk-' + 'a' * 32), '')
        self.assertEqual(server.key_format_problem(''), '')

    def test_uuid_is_recognised(self):
        self.assertIn('UUID', server.key_format_problem('11111111-2222-3333-4444-555555555555'))

    def test_missing_sk_prefix(self):
        self.assertIn('sk-', server.key_format_problem('abc123def456'))

    def test_wrong_length(self):
        self.assertIn('35', server.key_format_problem('sk-' + 'a' * 40))

    def test_key_tail(self):
        self.assertEqual(server.key_tail('sk-abcdef'), 'cdef')
        self.assertEqual(server.key_tail(''), '')

    def test_401_error_mentions_tail_and_uuid(self):
        bad = '11111111-2222-3333-4444-555555555555'
        err = urllib.error.HTTPError('https://api.deepseek.com', 401, 'err', {},
                                     io.BytesIO(b'{"error":{"message":"Authentication Fails"}}'))
        msg = server._llm_error(err, bad)
        self.assertIn('5555', msg)
        self.assertIn('UUID', msg)


class TestIgnore(TempApp):
    """忽略名单：按项目名称记住，扫描时自动跳过，也能撤销。"""

    def test_add_and_list(self):
        r = server.add_ignore(u'某个包.7z', r'D:\Downloads\某个包.7z')
        self.assertEqual(r['total'], 1)
        recs = server.load_ignore()
        self.assertEqual(recs[0]['name'], u'某个包.7z')
        self.assertTrue(recs[0]['addedAt'], u'应该记录加入时间')

    def test_add_is_case_insensitive_and_deduped(self):
        server.add_ignore('Foo.zip')
        server.add_ignore('foo.ZIP')
        self.assertEqual(len(server.load_ignore()), 1)

    def test_blank_name_rejected(self):
        with self.assertRaises(ValueError):
            server.add_ignore('   ')

    def test_is_ignored_by_name_or_path(self):
        server.add_ignore('foo.zip', r'D:\Downloads\foo.zip')
        self.assertTrue(server.is_ignored(Path(r'D:\Elsewhere\FOO.ZIP')))
        self.assertTrue(server.is_ignored(Path(r'D:\Downloads\foo.zip')))
        self.assertFalse(server.is_ignored(Path(r'D:\Downloads\bar.zip')))

    def test_remove_ignore(self):
        server.add_ignore('foo.zip')
        self.assertTrue(server.remove_ignore('FOO.ZIP')['removed'])
        self.assertFalse(server.is_ignored(Path('foo.zip')))
        self.assertFalse(server.remove_ignore('nothing.zip')['removed'])

    def test_finalize_drops_ignored_items(self):
        server.add_ignore('foo.zip')
        data = {'items': [{'name': 'foo.zip', 'path': r'D:\a\foo.zip'},
                          {'name': 'bar.zip', 'path': r'D:\a\bar.zip'}]}
        out = server._finalize(data)
        self.assertEqual([x['name'] for x in out['items']], ['bar.zip'])
        self.assertEqual(out['items'][0]['note'], '', u'保留项仍要附带备注字段')

    def test_handwritten_snapshot_with_string_names(self):
        server.IGNORE_FILE.write_text(json.dumps({'names': ['foo.zip']}), encoding='utf-8')
        data = {'items': [{'name': 'FOO.ZIP', 'path': r'D:\a\FOO.ZIP'}]}
        self.assertEqual(server._finalize(data)['items'], [])


class TestIgnoreDuringScan(TempApp):
    """重新扫描时直接跳过被忽略的项目，旧快照里的也要过滤掉。"""

    def setUp(self):
        super().setUp()
        self.root = self.dir / 'Downloads'
        self.root.mkdir()
        (self.root / 'keepme.zip').write_bytes(b'x' * 10)
        (self.root / 'ignoredme.zip').write_bytes(b'x' * 10)
        self._classify = server.classify_first_level
        server.classify_first_level = lambda items: {}
        server.roots = lambda: [self.root]

    def tearDown(self):
        server.classify_first_level = self._classify
        super().tearDown()

    def test_ignored_name_skipped_on_rescan(self):
        server.add_ignore('ignoredme.zip')
        names = [x['name'] for x in server.scan(True)['items']]
        self.assertIn('keepme.zip', names)
        self.assertNotIn('ignoredme.zip', names)

    def test_stale_cached_snapshot_is_cleaned(self):
        data = {'generatedAt': '2026-01-01T00:00:00', 'roots': [str(self.root)], 'errors': [],
                'items': [{'name': 'ignoredme.zip', 'path': str(self.root / 'ignoredme.zip')},
                          {'name': 'keepme.zip', 'path': str(self.root / 'keepme.zip')}]}
        server.save_json_file(server.SNAPSHOT_FILE, data)
        server.CACHE.clear()
        server.add_ignore('ignoredme.zip')
        names = [x['name'] for x in server.scan(False)['items']]
        self.assertNotIn('ignoredme.zip', names)


class TestConnectionProbe(TempApp):
    """回归：401 分支用过未定义的 tail，界面会显示 name 'tail' is not defined。"""

    def setUp(self):
        super().setUp()
        self.env = FakeEnv()
        self._set_env = server.set_user_env_key
        self._env_key = server.env_api_key
        server.set_user_env_key = self.env
        server.env_api_key = lambda: self.env.stored.get(server.ENV_KEY_NAME, '')
        self._urlopen = urllib.request.urlopen

    def tearDown(self):
        urllib.request.urlopen = self._urlopen
        server.set_user_env_key = self._set_env
        server.env_api_key = self._env_key
        super().tearDown()

    def _raise_401(self, req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, 'Unauthorized', {},
                                     io.BytesIO(b'{"error":{"message":"Authentication Fails"}}'))

    def test_401_returns_friendly_message_not_nameerror(self):
        self.env.stored[server.ENV_KEY_NAME] = '11111111-2222-3333-4444-555555555555'
        urllib.request.urlopen = self._raise_401
        out = server.test_connection()
        self.assertFalse(out['ok'])
        self.assertNotIn('is not defined', out['error'])
        self.assertIn('5555', out['error'])
        self.assertIn('UUID', out['error'])
        self.assertEqual(out['keyTail'], '5555')

    def test_401_with_good_looking_key_asks_to_refill(self):
        self.env.stored[server.ENV_KEY_NAME] = 'sk-' + 'a' * 32
        urllib.request.urlopen = self._raise_401
        out = server.test_connection()
        self.assertFalse(out['ok'])
        self.assertIn('aaaa', out['error'])
        self.assertIn(u'模型设置', out['error'])


if __name__ == '__main__':
    unittest.main()
