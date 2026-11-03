"""Verify migrations preserve unrelated directory/admin data and are reversible."""
import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('migration', Path(__file__).with_name('deploy')/'migrate_ip2626.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'config').mkdir()
        (self.root/'data').mkdir()
        self.config = self.root/'config/directory.json'
        self.database = self.root/'data/directory.sqlite3'
        self.backup = self.root/'backup'
        self.config.write_text(json.dumps({'database':'../data/directory.sqlite3',
            'bootstrap_admin':{'id':'owner','key_hash':'saved-test-hash'},
            'initial_servers':[{'id':'friends-main','url':migration.OLD}]}), 'utf-8')
        with closing(sqlite3.connect(self.database)) as db, db:
            db.executescript('CREATE TABLE servers(id TEXT PRIMARY KEY,name TEXT,url TEXT UNIQUE,locked INTEGER,enabled INTEGER);'
                             'CREATE TABLE admins(id TEXT PRIMARY KEY,key_hash TEXT);')
            db.execute('INSERT INTO servers VALUES(?,?,?,?,?)',('friends-main','好友房间',migration.OLD,0,1))
            db.execute('INSERT INTO servers VALUES(?,?,?,?,?)',('other','Other','https://example.invalid',1,1))
            db.execute('INSERT INTO admins VALUES(?,?)',('owner','saved-test-hash'))

    def snapshot(self):
        with closing(sqlite3.connect(self.database)) as db:
            return [list(db.execute('SELECT * FROM '+table+' ORDER BY id')) for table in ('servers','admins')]

    def test_roundtrip_preserves_admins_and_other_servers(self):
        original = self.snapshot()
        config = self.config.read_bytes()
        migration.migrate(self.root,self.backup)
        updated = self.snapshot()
        expected = [list(original[0]),list(original[1])]
        entry = list(expected[0][0]);entry[2] = migration.NEW;expected[0][0] = tuple(entry)
        self.assertEqual(expected, updated)
        self.assertTrue((self.backup/'directory.sqlite3').is_file())
        migration.migrate(self.root,self.backup,True)
        self.assertEqual(original,self.snapshot())
        self.assertEqual(config,self.config.read_bytes())

    def test_custom_url_refused_without_changes(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE servers SET url='https://custom.invalid' WHERE id='friends-main'")
        original = self.snapshot()
        with self.assertRaises(RuntimeError):migration.migrate(self.root,self.backup)
        self.assertEqual(original,self.snapshot())

    def test_custom_initial_url_refused_before_database_change(self):
        config = json.loads(self.config.read_text('utf-8'))
        config['initial_servers'][0]['url'] = 'https://custom.invalid'
        self.config.write_text(json.dumps(config),'utf-8')
        original = self.snapshot()
        with self.assertRaises(RuntimeError):migration.migrate(self.root,self.backup)
        self.assertEqual(original,self.snapshot())


if __name__ == '__main__':unittest.main()
