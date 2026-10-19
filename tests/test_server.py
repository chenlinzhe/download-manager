# -*- coding: utf-8 -*-
"""下载包管家 - server 纯逻辑单元测试（stdlib unittest，无需额外依赖）。
运行：python -m unittest discover -s tests -v
"""
import io, json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
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
                     'MANUAL_ROOTS_FILE', 'NOTES_FILE', 'IGNORE_FILE', 'GROUPS_FILE'):
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


class TestUnkeep(TempApp):
    """取消保留：标签要删掉，建议要立刻按当前磁盘情况重算。"""

    def setUp(self):
        super().setUp()
        self.root = self.dir / '下载'
        self.pkg = self.root / 'tool'
        self.pkg.mkdir(parents=True)
        (self.pkg / 'setup.exe').write_bytes(b'x' * 32)
        server.roots = lambda: [self.root]

    def test_keep_then_unkeep_restores_score(self):
        server.save_keep([str(self.pkg)])
        self.assertEqual(server.load_labels()[str(self.pkg.resolve()).lower()]['label'], 'keep')
        before = server.reanalyze(str(self.pkg))
        self.assertEqual(before['recommendation'], '保留（手工）')
        self.assertEqual(before['score'], 100)
        out = server.remove_keep([str(self.pkg)])
        self.assertEqual(len(out['removed']), 1)
        self.assertEqual(server.load_labels(), {})
        fresh = out['refreshed'][0]
        self.assertNotIn('manualKeep', fresh)
        self.assertLess(fresh['score'], 100)
        self.assertNotEqual(fresh['recommendation'], '保留（手工）')
        self.assertEqual(fresh['files'], 1)

    def test_unkeep_not_marked_is_noop(self):
        out = server.remove_keep([str(self.pkg)])
        self.assertEqual(out, {'removed': [], 'refreshed': []})

    def test_unkeep_syncs_cached_snapshot(self):
        item = {'name': 'tool', 'path': str(self.pkg), 'score': 100,
                'recommendation': '保留（手工）', 'manualKeep': True, 'reasons': ['x']}
        server.save_json_file(server.SNAPSHOT_FILE,
                              {'generatedAt': '2026-01-01T00:00:00', 'roots': [str(self.root)],
                               'errors': [], 'items': [dict(item)]})
        server.CACHE.clear(); server.CACHE.update({'items': [dict(item)], 'at': 0})
        server.save_keep([str(self.pkg)])
        server.remove_keep([str(self.pkg)])
        snap = server.load_json_file(server.SNAPSHOT_FILE, {})
        self.assertNotIn('manualKeep', snap['items'][0])
        self.assertNotEqual(snap['items'][0]['recommendation'], '保留（手工）')

    def test_reanalyze_rejects_outside_paths(self):
        outside = self.dir / 'not-a-root'
        outside.mkdir()
        with self.assertRaises(ValueError):
            server.reanalyze(str(outside))

    def test_reanalyze_missing_path_reported(self):
        with self.assertRaises(ValueError):
            server.reanalyze(str(self.root / 'gone'))


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
        out = server.save_settings({'apiKey': 'sk-' + 'a' * 32, 'autoAnalyze': False})
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
        server.save_settings({'apiKey': 'sk-' + 'c' * 32, 'autoAnalyze': False})
        server.save_settings({'clearApiKey': True})
        self.assertEqual(server.get_settings(True)['apiKey'], '')
        self.assertFalse(server.get_settings(False)['apiKeyMasked'])
        self.assertNotIn('apiKeyEnc', self._raw())
        self.assertFalse(server.get_settings(True)['autoAnalyze'], '清除 Key 不应把 autoAnalyze 打回 True')

    def test_env_key_wins_over_file(self):
        server.SETTINGS_FILE.write_text(json.dumps({'apiKeyEnc': server.protect_key('sk-file')}), encoding='utf-8')
        self.env.stored[server.ENV_KEY_NAME] = 'sk-env'
        self.assertEqual(server.get_settings(True)['apiKey'], 'sk-env')
        self.assertEqual(server.get_settings(False)['keySource'], 'env')

    def test_legacy_file_key_migrates_to_env_on_save(self):
        server.SETTINGS_FILE.write_text(json.dumps({'apiKey': 'sk-legacy'}), encoding='utf-8')
        out = server.save_settings({'autoAnalyze': True})
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


class TestAutoAnalyzeSwitch(TempApp):
    """启动时自动 AI 分析：默认关闭，旧版的开关不再生效。"""

    def setUp(self):
        super().setUp()
        self._env_key = server.env_api_key
        server.env_api_key = lambda: ''

    def tearDown(self):
        server.env_api_key = self._env_key
        super().tearDown()

    def test_default_is_off(self):
        self.assertFalse(server.get_settings(True)['autoAnalyze'])

    def test_legacy_autoSearch_on_is_ignored(self):
        server.SETTINGS_FILE.write_text(json.dumps({'autoSearch': True}), encoding='utf-8')
        cfg = server.get_settings(True)
        self.assertFalse(cfg['autoAnalyze'], '旧版 autoSearch=true 不该再让软件每次启动都分析')
        self.assertNotIn('autoSearch', cfg)

    def test_switch_can_be_turned_on_and_persists(self):
        server.save_settings({'autoAnalyze': True})
        self.assertTrue(server.get_settings(True)['autoAnalyze'])
        server.save_settings({'baseUrl': 'https://api.deepseek.com'})
        self.assertTrue(server.get_settings(True)['autoAnalyze'], '保存其它设置不该把开关打回 False')
        self.assertNotIn('autoSearch', json.loads(server.SETTINGS_FILE.read_text(encoding='utf-8')))


class TestArchiveEntries(unittest.TestCase):
    """AI 分析前只读压缩包里的文件清单（不解压到磁盘）。"""

    def test_lists_zip_entries_without_extracting(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'WeChatSetup.zip'
            with zipfile.ZipFile(str(p), 'w') as z:
                z.writestr('WeChat.exe', b'x' * 10)
                z.writestr('readme.txt', 'hello')
                z.writestr('plugins/', '')
            names = server.archive_entry_list(str(p))
            self.assertIn('WeChat.exe', names)
            self.assertIn('readme.txt', names)
            self.assertFalse([n for n in names if n.endswith('/')], '目录项不该进清单')
            self.assertEqual([f.name for f in Path(td).iterdir()], ['WeChatSetup.zip'],
                             '不该把压缩包解压出任何文件')

    def test_empty_for_non_archive_missing_and_blank(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'note.txt'
            p.write_text('hello', encoding='utf-8')
            self.assertEqual(server.archive_entry_list(str(p)), [])
            self.assertEqual(server.archive_entry_list(str(Path(td) / 'nope.zip')), [])
        self.assertEqual(server.archive_entry_list(''), [])
        self.assertEqual(server.archive_entry_list(None), [])

    def test_entry_list_is_capped(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'many.zip'
            with zipfile.ZipFile(str(p), 'w') as z:
                for i in range(40):
                    z.writestr('f%02d.txt' % i, 'x')
            self.assertEqual(len(server.archive_entry_list(str(p), limit=5)), 5)

    def test_description_prompt_mentions_archive_contents(self):
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'WeChatSetup.zip'
            with zipfile.ZipFile(str(p), 'w') as z:
                z.writestr('WeChat.exe', b'x')
            prompt = server.description_prompt({'name': 'WeChatSetup.zip', 'path': str(p)})
            self.assertIn('WeChatSetup.zip', prompt)
            self.assertIn('WeChat.exe', prompt)
            self.assertIn(u'压缩包', prompt)
            self.assertIn('summary', prompt)

    def test_description_prompt_without_archive_stays_short(self):
        prompt = server.description_prompt({'name': 'tool.zip'})
        self.assertIn('tool.zip', prompt)
        self.assertNotIn(u'压缩包', prompt)


class TestEnrichForce(TempApp):
    """AI 分析缓存：文件没变就直接复用，按住 Shift（force=True）才重做。"""

    def setUp(self):
        super().setUp()
        self.items = [
            {'path': 'D:/dl/WeChatSetup.exe', 'name': 'WeChatSetup.exe', 'size': 100,
             'modified': '2026-01-01T00:00:00'},
            {'path': 'D:/dl/Tool.zip', 'name': 'Tool.zip', 'size': 200,
             'modified': '2026-02-02T00:00:00'},
        ]
        self._cache = server.CACHE
        server.CACHE = {'items': list(self.items)}
        self._desc = server.deepseek_description
        self.calls = []

        def fake_desc(item):
            self.calls.append(item['path'])
            return {'summary': u'第%d次分析的说明' % len(self.calls)}
        server.deepseek_description = fake_desc
        self.old = {'summary': u'很久以前的说明',
                    'searchedAt': '2020-01-01T00:00:00', 'model': 'deepseek-chat'}
        server.save_json_file(server.AI_CACHE_FILE, {
            server.item_fingerprint(self.items[0]): dict(self.old)})

    def tearDown(self):
        server.deepseek_description = self._desc
        server.CACHE = self._cache
        super().tearDown()

    def test_cache_hit_returns_without_calling_api(self):
        out = server.enrich_items([self.items[0]['path']])
        self.assertEqual(self.calls, [], u'文件没变就不该再花一次 API 调用')
        self.assertTrue(out['ok'])
        self.assertEqual(out['result'][self.items[0]['path']]['summary'], u'很久以前的说明')
        self.assertEqual(out['result'][self.items[0]['path']]['searchedAt'], '2020-01-01T00:00:00')

    def test_force_reruns_analysis_and_refreshes_time(self):
        out = server.enrich_items([self.items[0]['path']], True)
        self.assertEqual(self.calls, [self.items[0]['path']], u'force=True 必须真的再问一次 AI')
        got = out['result'][self.items[0]['path']]
        self.assertEqual(got['summary'], u'第1次分析的说明')
        self.assertNotEqual(got['searchedAt'], '2020-01-01T00:00:00')
        self.assertTrue(got['searchedAt'] > '2020-01-01T00:00:00')
        saved = server.load_json_file(server.AI_CACHE_FILE, {})
        self.assertEqual(saved[server.item_fingerprint(self.items[0])]['summary'],
                         u'第1次分析的说明', u'重做的结果要写回缓存文件')

    def test_uncached_item_is_analyzed(self):
        out = server.enrich_items([self.items[1]['path']])
        self.assertEqual(self.calls, [self.items[1]['path']])
        self.assertEqual(out['result'][self.items[1]['path']]['summary'], u'第1次分析的说明')

    def test_changed_file_is_not_served_from_cache(self):
        changed = dict(self.items[0])
        changed['size'] = 999
        server.CACHE = {'items': [changed]}
        out = server.enrich_items([changed['path']])
        self.assertEqual(self.calls, [changed['path']], u'大小变了就得重新分析')
        self.assertEqual(out['result'][changed['path']]['summary'], u'第1次分析的说明')

    def test_mixed_batch_only_asks_for_missing_ones(self):
        out = server.enrich_items([self.items[0]['path'], self.items[1]['path']])
        self.assertEqual(self.calls, [self.items[1]['path']])
        self.assertEqual(len(out['result']), 2)


# -*- coding: utf-8 -*-
class TestResourceGroups(TempApp):
    """资源标签：第一个固定是「下载包」，用户可以自己新建（例如「我的项目」）并往里加目录。"""

    def setUp(self):
        super().setUp()
        self.proj = self.dir / 'myproject'
        self.proj.mkdir()
        self.dl = self.dir / 'downloads'
        self.dl.mkdir()
        # 内置组的目录来源固定成一个临时目录，避免依赖真实磁盘
        server.roots = lambda: [self.dl]

    def test_first_group_is_builtin_download(self):
        gs = server.groups()
        self.assertEqual(gs[0]['id'], 'download')
        self.assertEqual(gs[0]['name'], u'下载包')
        self.assertTrue(gs[0]['builtin'])
        self.assertEqual(gs[0]['roots'], [str(self.dl)])

    def test_add_group_and_rename(self):
        g = server.add_group(u'我的项目')
        self.assertEqual(g['name'], u'我的项目')
        self.assertEqual(g['roots'], [])
        self.assertIn(u'我的项目', [x['name'] for x in server.groups()])
        out = server.rename_group(g['id'], u'项目资料')
        self.assertEqual(out['name'], u'项目资料')
        self.assertIn(u'项目资料', [x['name'] for x in server.groups()])

    def test_duplicate_blank_and_builtin_names_rejected(self):
        server.add_group(u'我的项目')
        for bad in (u'我的项目', u'   ', u'下载包'):
            with self.assertRaises(ValueError):
                server.add_group(bad)

    def test_builtin_group_cannot_be_renamed(self):
        with self.assertRaises(ValueError):
            server.rename_group('download', u'别的名字')

    def test_name_is_trimmed_and_capped(self):
        self.assertEqual(server.add_group(u'  我的   项目  ')['name'], u'我的 项目')
        self.assertEqual(len(server.add_group('x' * 80)['name']), 24,
                         u'标签最长 24 字，避免把标签条撑坏')

    def test_manual_root_goes_into_that_group(self):
        g = server.add_group(u'我的项目')
        server.add_manual_root(str(self.proj), g['id'])
        row = [x for x in server.groups() if x['id'] == g['id']][0]
        self.assertEqual(row['roots'], [str(self.proj.resolve())])
        self.assertTrue(server.allowed(self.proj / 'inner.zip'),
                        u'用户自己标签下的目录也要能参与保留 / 转移 / 回收站')
        self.assertEqual(server.add_manual_root(str(self.proj)), str(self.proj.resolve()),
                         u'同一个目录不会同时进两个标签，重复添加时原样返回')
        self.assertEqual(server.load_json_file(server.MANUAL_ROOTS_FILE, []), [],
                         u'已经在「我的项目」里了，不该再塞进内置的「下载包」')
        extra = self.dir / 'extra'
        extra.mkdir()
        server.add_manual_root(str(extra))
        self.assertIn(str(extra.resolve()), server.load_json_file(server.MANUAL_ROOTS_FILE, []),
                      u'不指定标签时目录仍然加到内置的「下载包」')

    def test_unknown_group_is_rejected(self):
        with self.assertRaises(ValueError):
            server.add_manual_root(str(self.proj), 'nope')

    def test_finalize_attaches_group_summary(self):
        g = server.add_group(u'我的项目')
        data = server._finalize({'items': [
            {'name': 'a.zip', 'path': str(self.dl / 'a.zip'), 'root': str(self.dl), 'size': 1},
            {'name': 'proj1', 'path': str(self.proj / 'proj1'), 'root': str(self.proj),
             'group': g['id'], 'size': 1}]})
        byid = {x['id']: x for x in data['groups']}
        self.assertEqual(byid['download']['count'], 1)
        self.assertEqual(byid[g['id']]['count'], 1)
        self.assertEqual(data['items'][0]['groupName'], u'下载包')
        self.assertEqual(data['items'][1]['groupName'], u'我的项目')

class TestAddManualRoots(TempApp):
    """一次加多个目录（资源管理器里按住 Ctrl / Shift 多选）。"""

    def setUp(self):
        super().setUp()
        self.dl = self.dir / 'downloads'
        self.dl.mkdir()
        server.roots = lambda: [self.dl]
        self.a = self.dir / 'proj-a'
        self.b = self.dir / 'proj-b'
        self.c = self.dir / 'proj-c'
        for p in (self.a, self.b, self.c):
            p.mkdir()

    def test_many_at_once(self):
        g = server.add_group(u'我的项目')
        out = server.add_manual_roots([str(self.a), str(self.b), str(self.c)], g['id'])
        self.assertEqual(out['added'], [str(self.a.resolve()), str(self.b.resolve()), str(self.c.resolve())])
        self.assertEqual(out['skipped'], [])
        self.assertEqual(out['failed'], [])
        self.assertEqual(out['groupName'], u'我的项目')
        row = [x for x in server.groups() if x['id'] == g['id']][0]
        self.assertEqual(sorted(row['roots']), sorted(out['added']))

    def test_duplicates_are_skipped(self):
        g = server.add_group(u'我的项目')
        server.add_manual_roots([str(self.a)], g['id'])
        out = server.add_manual_roots([str(self.a), str(self.b), str(self.b)], g['id'])
        self.assertEqual(out['added'], [str(self.b.resolve())])
        self.assertEqual(len(out['skipped']), 2)
        self.assertIn(u'已经在这个标签里了', out['skipped'][0]['reason'])
        self.assertIn(u'两次', out['skipped'][1]['reason'])

    def test_folder_of_another_label_is_skipped(self):
        g = server.add_group(u'我的项目')
        server.add_manual_roots([str(self.a)], g['id'])
        out = server.add_manual_roots([str(self.a)], 'download')
        self.assertEqual(out['added'], [])
        self.assertIn(u'我的项目', out['skipped'][0]['reason'])
        self.assertEqual(server.load_json_file(server.MANUAL_ROOTS_FILE, []), [])

    def test_missing_folder_reports_failure_but_keeps_others(self):
        g = server.add_group(u'我的项目')
        out = server.add_manual_roots([str(self.dir / 'nope'), str(self.a)], g['id'])
        self.assertEqual(out['added'], [str(self.a.resolve())])
        self.assertEqual(len(out['failed']), 1)
        self.assertIn(u'不是有效目录', out['failed'][0]['error'])

    def test_unknown_group_is_rejected(self):
        with self.assertRaises(ValueError):
            server.add_manual_roots([str(self.a)], 'nope')

    def test_builtin_group_takes_many(self):
        out = server.add_manual_roots([str(self.a), str(self.b)])
        self.assertEqual(len(out['added']), 2)
        saved = server.load_json_file(server.MANUAL_ROOTS_FILE, [])
        self.assertEqual(sorted(saved), sorted([str(self.a.resolve()), str(self.b.resolve())]))

    def test_empty_list_changes_nothing(self):
        g = server.add_group(u'我的项目')
        out = server.add_manual_roots([], g['id'])
        self.assertEqual((out['added'], out['skipped'], out['failed']), ([], [], []))
        self.assertEqual([x for x in server.groups() if x['id'] == g['id']][0]['roots'], [])

class TestScanCache(TempApp):
    """回归（V1.9 的 bug）：加了目录之后点扫描必须真的变新，不能拿旧快照 / 旧内存缓存糊弄。"""

    def setUp(self):
        super().setUp()
        self.root_a = self.dir / 'rootA'
        (self.root_a / 'alpha').mkdir(parents=True)
        (self.root_a / 'alpha' / 'a.zip').write_bytes(b'x')
        self.root_b = self.dir / 'rootB'
        (self.root_b / 'gamma').mkdir(parents=True)
        (self.root_b / 'gamma' / 'c.zip').write_bytes(b'x')
        self._classify = server.classify_first_level
        server.classify_first_level = lambda children: {}
        self._cache = server.CACHE
        server.CACHE = {}
        self.group = server.add_group(u'我的项目')

    def tearDown(self):
        server.classify_first_level = self._classify
        server.CACHE = self._cache
        super().tearDown()

    def names(self, data):
        return sorted(x['name'] for x in data['items'])

    def test_new_folder_shows_up_without_forced_rescan(self):
        server.add_manual_roots([str(self.root_a)], self.group['id'])
        self.assertEqual(self.names(server.scan(False)), ['alpha'])
        server.add_manual_roots([str(self.root_b)], self.group['id'])
        data = server.scan(False)
        self.assertEqual(self.names(data), ['alpha', 'gamma'],
                         u'目录清单变了就必须重扫，不能复用 7 天内的旧快照')
        self.assertFalse(data.get('reused'), u'这是刚扫出来的，界面上不能写「复用」')

    def test_unchanged_roots_still_reuse_snapshot(self):
        server.add_manual_roots([str(self.root_a)], self.group['id'])
        first = server.scan(False)
        second = server.scan(False)
        self.assertEqual(first['generatedAt'], second['generatedAt'], u'清单没变就该复用，保持打开速度快')
        self.assertFalse(first.get('reused'), u'第一次是真扫')
        self.assertTrue(second.get('reused'), u'第二次是复用，界面据此写「复用最近扫描结果」')

    def test_removed_folder_disappears(self):
        server.add_manual_roots([str(self.root_a), str(self.root_b)], self.group['id'])
        self.assertEqual(self.names(server.scan(False)), ['alpha', 'gamma'])
        server.add_manual_roots([], self.group['id'])
        server.save_json_file(server.GROUPS_FILE, [{'id': self.group['id'], 'name': u'我的项目', 'roots': [str(self.root_a)]}])
        self.assertEqual(self.names(server.scan(False)), ['alpha'], u'删掉目录后旧列表不能继续留着')

    def test_forced_scan_waits_instead_of_returning_stale_cache(self):
        server.add_manual_roots([str(self.root_a)], self.group['id'])
        server.scan(True)
        self.assertEqual(self.names(server.scan(False)), ['alpha'])
        server.add_manual_roots([str(self.root_b)], self.group['id'])
        hold = threading.Event()
        release = threading.Event()

        def hold_lock():
            server.SCAN_LOCK.acquire()
            hold.set()
            release.wait(15)
            server.SCAN_LOCK.release()

        worker = threading.Thread(target=hold_lock)
        worker.start()
        self.assertTrue(hold.wait(5))
        threading.Timer(0.4, release.set).start()
        threading.Timer(12, release.set).start()   # 保险：测试绝不能挂死
        data = server.scan(True)
        release.set()
        worker.join(15)
        self.assertEqual(self.names(data), ['alpha', 'gamma'],
                         u'上一次扫描还没跑完时再点「重新扫描」，必须等它结束并给出真正的新结果')
        self.assertEqual(server.scan_status().get('phase'), '', u'结束后进度要清空')


class TestScanAiSwitch(TempApp):
    """扫描是否允许调用 AI：默认关闭（纯本地），打开后才会问 DeepSeek。"""

    def setUp(self):
        super().setUp()
        self.root = self.dir / 'dl'
        (self.root / 'project-x' / 'src').mkdir(parents=True)
        (self.root / 'project-x' / 'docs').mkdir()
        self.group = server.add_group(u'我的项目')
        server.add_manual_roots([str(self.root)], self.group['id'])
        self._cache = server.CACHE
        server.CACHE = {}
        self.calls = []
        self._classify = server.classify_collection
        server.classify_collection = self._fake_classify

    def _fake_classify(self, path):
        self.calls.append(str(path))
        return {'isCollection': True, 'reason': u'多个独立包'}

    def tearDown(self):
        server.classify_collection = self._classify
        server.CACHE = self._cache
        super().tearDown()

    def test_switch_defaults_to_off(self):
        self.assertFalse(server.get_settings(True).get('scanAI'))
        self.assertFalse(server.scan_ai_enabled())

    def test_switch_persists(self):
        out = server.save_settings({'scanAI': True})
        self.assertTrue(out.get('scanAI'))
        self.assertTrue(server.get_settings(True)['scanAI'])
        self.assertTrue(server.scan_ai_enabled())

    def test_scan_does_not_call_ai_by_default(self):
        data = server.scan(True)
        self.assertEqual(self.calls, [], u'扫描默认不该联网问 AI')
        row = [x for x in data['items'] if x['name'] == 'project-x'][0]
        self.assertTrue(row.get('collectionPending'), u'拿不准的目录要标记成待判断')

    def test_switch_on_judges_and_expands(self):
        server.save_settings({'scanAI': True})
        data = server.scan(True)
        self.assertEqual(len(self.calls), 1, u'打开开关后每个拿不准的目录问一次')
        self.assertEqual(sorted(x['name'] for x in data['items']), ['docs', 'src'])

    def test_local_rule_still_expands_without_ai(self):
        packs = self.root / 'packs'
        packs.mkdir()
        (packs / 'a.zip').write_bytes(b'x')
        (packs / 'b.zip').write_bytes(b'x')
        data = server.scan(True)
        self.assertEqual(self.calls, [])
        self.assertEqual(sorted(x['name'] for x in data['items']), ['a.zip', 'b.zip', 'project-x'])


if __name__ == '__main__':
    unittest.main()


class TestScanSpeed(TempApp):
    """V2.1：统计大小/文件数时跳过依赖与缓存目录，否则大项目要扫十几分钟。"""

    def test_summary_skips_dependency_dirs(self):
        root = self.dir / 'proj'
        (root / 'src').mkdir(parents=True)
        (root / 'src' / 'a.py').write_bytes(b'x' * 10)
        pkg = root / 'node_modules' / 'pkg'
        pkg.mkdir(parents=True)
        for i in range(50):
            (pkg / ('f%d.js' % i)).write_bytes(b'x' * 100)
        size, files, dirs, newest, hints, err = server.summary(root)
        self.assertEqual(files, 1, u'node_modules 里的文件不该一个个数进来')
        self.assertEqual(size, 10)
        self.assertEqual(dirs, 2, u'src 与 node_modules 都算一个目录，但不进去数 pkg')
        self.assertEqual(err, 0)

    def test_summary_uses_scandir_and_keeps_normal_dirs(self):
        root = self.dir / 'proj2'
        (root / 'a' / 'b').mkdir(parents=True)
        (root / 'a' / 'b' / 'crack_tool.exe').write_bytes(b'y' * 5)
        size, files, dirs, newest, hints, err = server.summary(root)
        self.assertEqual((files, dirs, size), (1, 2, 5))
        self.assertIn('crack_tool.exe', hints, u'破解提示照旧要认出来')


class TestGroupList(TempApp):
    """V2.1：界面启动时先用 group_list 把标签条画出来，不能为此触发一次扫描。"""

    def setUp(self):
        super().setUp()
        self._cache = server.CACHE
        server.CACHE = {}
        self.root_a = self.dir / 'rootA'
        (self.root_a / 'alpha').mkdir(parents=True)
        (self.root_a / 'alpha' / 'a.zip').write_bytes(b'x')
        self._classify = server.classify_first_level
        server.classify_first_level = lambda children: {}
        self.group = server.add_group(u'我的项目')

    def tearDown(self):
        server.classify_first_level = self._classify
        server.CACHE = self._cache
        super().tearDown()

    def test_group_list_reads_snapshot_without_scanning(self):
        server.add_manual_roots([str(self.root_a)], self.group['id'])
        server.scan(True)
        called = []
        orig = server._scan_impl
        server._scan_impl = lambda *a, **k: called.append(1)
        try:
            rows = server.group_list()
        finally:
            server._scan_impl = orig
        self.assertEqual(called, [], u'画标签条不许触发扫描')
        by_id = {r['id']: r for r in rows}
        self.assertIn('download', by_id, u'第一个标签永远是「下载包」')
        self.assertEqual(by_id[self.group['id']]['count'], 1, u'条目数来自上次扫描结果')
        self.assertEqual(by_id[self.group['id']]['name'], u'我的项目')
        self.assertEqual(by_id[self.group['id']]['roots'], [str(self.root_a)])


class TestNoticeSetting(TempApp):
    """V2.2：顶部提示条点过 ✕ 之后就不再自动显示（记住「下次是否再显示」）。"""

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

    def test_notice_is_shown_by_default(self):
        self.assertFalse(server.get_settings(False)['hideNotice'], u'默认要显示提示条')

    def test_closing_notice_is_remembered(self):
        server.save_settings({'hideNotice': True})
        self.assertTrue(server.get_settings(False)['hideNotice'])
        raw = json.loads(server.SETTINGS_FILE.read_text(encoding='utf-8'))
        self.assertTrue(raw['hideNotice'], u'「不再显示」要写进本机设置')

    def test_partial_save_keeps_notice_choice(self):
        server.save_settings({'hideNotice': True})
        server.save_settings({'apiKey': 'sk-' + 'd' * 32})  # 只改 Key，不碰提示条
        self.assertTrue(server.get_settings(False)['hideNotice'], u'保存别的设置不应把提示条重新打开')

    def test_can_turn_notice_back_on(self):
        server.save_settings({'hideNotice': True})
        server.save_settings({'hideNotice': False})
        self.assertFalse(server.get_settings(False)['hideNotice'])


class TestCli(TempApp):
    """V2.2：命令行入口给 GPT / dsh 等外部工具读数据，默认只读快照、不扫描、不联网。"""

    def setUp(self):
        super().setUp()
        import cli
        self.cli = cli
        self._cache = server.CACHE
        server.CACHE = {}
        self._classify = server.classify_first_level
        server.classify_first_level = lambda children: {}
        self.env = FakeEnv()
        self._set_env = server.set_user_env_key
        self._env_key = server.env_api_key
        server.set_user_env_key = self.env
        server.env_api_key = lambda: ''
        self.root = self.dir / 'rootA'
        (self.root / 'alpha').mkdir(parents=True)
        (self.root / 'alpha' / 'setup.zip').write_bytes(b'x' * 20)
        (self.root / 'beta').mkdir(parents=True)
        (self.root / 'beta' / 'tool.exe').write_bytes(b'y' * 40)
        self.group = server.add_group(u'我的项目')
        server.add_manual_roots([str(self.root)], self.group['id'])
        server.scan(True)

    def tearDown(self):
        server.classify_first_level = self._classify
        server.set_user_env_key = self._set_env
        server.env_api_key = self._env_key
        server.CACHE = self._cache
        super().tearDown()

    def argv(self, *args):
        return self.cli.build_parser().parse_args(list(args))

    def test_status_reports_snapshot_and_key_state(self):
        out = self.cli.cmd_status(self.argv('status'))
        self.assertTrue(out['ok'])
        self.assertEqual(out['version'], server.APP_VERSION)
        self.assertTrue(out['snapshot']['exists'])
        self.assertEqual(out['snapshot']['count'], 2)
        self.assertFalse(out['settings']['aiConfigured'], u'没配置 Key 时 aiConfigured 必须是 false')

    def test_groups_and_list(self):
        groups = self.cli.cmd_groups(self.argv('groups'))
        self.assertTrue(groups['ok'])
        by_id = {g['id']: g for g in groups['groups']}
        self.assertIn('download', by_id, u'第一个标签永远是「下载包」')
        self.assertEqual(by_id[self.group['id']]['count'], 2)
        listed = self.cli.cmd_list(self.argv('list', '--sort', 'size', '--limit', '1'))
        self.assertTrue(listed['ok'])
        self.assertEqual(listed['total'], 2)
        self.assertEqual(listed['count'], 1)
        self.assertEqual(listed['items'][0]['name'], 'beta', u'按大小倒序，beta 更大')

    def test_list_fields_projection(self):
        listed = self.cli.cmd_list(self.argv('list', '--fields', 'name,sizeHuman'))
        self.assertEqual(sorted(listed['items'][0].keys()), ['name', 'sizeHuman'])

    def test_search_is_local_and_needs_no_key(self):
        found = self.cli.cmd_search(self.argv('search', 'alpha'))
        self.assertTrue(found['ok'])
        self.assertGreaterEqual(found['count'], 1)
        self.assertEqual(found['items'][0]['name'], 'alpha')

    def test_describe_by_path_tail(self):
        out = self.cli.cmd_describe(self.argv('describe', 'beta'))
        self.assertTrue(out['ok'])
        self.assertEqual(out['item']['name'], 'beta')

    def test_out_writes_plain_utf8_json(self):
        target = self.dir / 'out' / 'list.json'
        code = self.cli.main(['list', '--out', str(target), '--pretty'])
        self.assertEqual(code, 0)
        raw = target.read_bytes()
        self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), u'不要写 BOM')
        data = json.loads(raw.decode('utf-8'))
        self.assertTrue(data['ok'])
        self.assertEqual(data['total'], 2)

    def test_missing_item_exits_nonzero(self):
        target = self.dir / 'nope.json'
        code = self.cli.main(['describe', u'不存在的条目', '--out', str(target)])
        self.assertEqual(code, 1)
        data = json.loads(target.read_text(encoding='utf-8'))
        self.assertFalse(data['ok'])
        self.assertIn('error', data)
