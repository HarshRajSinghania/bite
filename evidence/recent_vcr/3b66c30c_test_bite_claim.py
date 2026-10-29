from keboola.vcr.db_recorder import _RecordingCursor


class FakeCursor:
    description = [("A", "NUMBER")]

    def __init__(self):
        self.n = 0

    def execute(self, sql, parameters=None, **kw):
        self.n += 1

    def fetchall(self):
        return [(self.n,)]

    def close(self):
        pass


def test_two_executes_on_one_cursor_both_recorded():
    log = []
    cur = _RecordingCursor(FakeCursor(), log)
    cur.execute("select 1 from dual")
    cur.fetchall()
    cur.execute("select 2 from dual")
    cur.fetchall()
    cur.close()
    assert len(log) == 2
