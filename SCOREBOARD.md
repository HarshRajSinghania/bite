# Bite scoreboard

Bite asks one question about each recent change in a project: **if this change disappeared, would a test notice?**
It takes the change out, runs the project's own tests, and puts it back. Here is what it found on 20 well-known open
source projects in 5 languages.

This isn't a ranking. A change no test notices is often fine: a speed-up, a type hint, a tidy-up, or code for
another system. So we read every unnoticed change by hand. **Real gaps** are the few where a test could and should
notice, like a new public method that nothing calls. They are small gaps in the tests, not bugs. Each one links to its
commit.

**In total:** 567 changes checked, 349 noticed by a test, and 17 real gaps, all small, in 10 of the 20 projects.
The other 10 had none. Every gap below was rechecked on Oct 31 against each project's code as it is today: the
change was taken out of today's code and the tests still passed.

| Project | Language | Changes checked | Noticed by a test | Real gaps |
|---|---|---|---|---|
| [Click](https://github.com/pallets/click) | Python | 37 | 30 | 1 small: [`help` on custom setting types](https://github.com/pallets/click/commit/405a5481) |
| [marshmallow](https://github.com/marshmallow-code/marshmallow) | Python | 36 | 18 | 2 small: [ipaddress types in `TYPE_MAPPING`](https://github.com/marshmallow-code/marshmallow/commit/c38b48ec), [a stale name in `__all__`](https://github.com/marshmallow-code/marshmallow/commit/5429f0d4) |
| [more-itertools](https://github.com/more-itertools/more-itertools) | Python | 34 | 21 | none ✅ |
| [packaging](https://github.com/pypa/packaging) | Python | 38 | 37 | none ✅ |
| [pluggy](https://github.com/pytest-dev/pluggy) | Python | 32 | 22 | 1 small: [`DistFacade` from its old place](https://github.com/pytest-dev/pluggy/commit/755339bf) |
| [Rich](https://github.com/Textualize/rich) | Python | 37 | 15 | 1 small: [`<kbd>` keys in Markdown](https://github.com/Textualize/rich/commit/a9c4aaba) |
| [Express](https://github.com/expressjs/express) | JavaScript | 4 | 4 | none ✅ |
| [minimist](https://github.com/minimistjs/minimist) | JavaScript | 21 | 15 | none ✅ |
| [object-inspect](https://github.com/inspect-js/object-inspect) | JavaScript | 37 | 25 | none ✅ |
| [qs](https://github.com/ljharb/qs) | JavaScript | 40 | 40 | none ✅ |
| [chi](https://github.com/go-chi/chi) | Go | 27 | 22 | 1 small: [XML compression](https://github.com/go-chi/chi/commit/d7b767bc) |
| [cobra](https://github.com/spf13/cobra) | Go | 31 | 17 | 1 small: [completing map flags more than once](https://github.com/spf13/cobra/commit/756ba6da) |
| [go-humanize](https://github.com/dustin/go-humanize) | Go | 17 | 16 | none ✅ |
| [testify](https://github.com/stretchr/testify) | Go | 32 | 16 | 1 small: [`Helper()` in IsIncreasing and friends](https://github.com/stretchr/testify/commit/65e0b94e) |
| [uuid](https://github.com/google/uuid) | Go | 21 | 13 | 4 small: [three of the error values](https://github.com/google/uuid/commit/0e97ed3b), [`NewString`](https://github.com/google/uuid/commit/bfb86fa4), [bad JSON in `NullUUID`](https://github.com/google/uuid/commit/44b5fee7), [`Max`](https://github.com/google/uuid/commit/c58770eb) |
| [anyhow](https://github.com/dtolnay/anyhow) | Rust | 22 | 1 | none ✅ |
| [bytes](https://github.com/tokio-rs/bytes) | Rust | 38 | 12 | 2 small: [`as_uninit_slice_mut`](https://github.com/tokio-rs/bytes/commit/b8d27c01), [`remaining_mut`](https://github.com/tokio-rs/bytes/commit/4b53a29e) |
| [indexmap](https://github.com/indexmap-rs/indexmap) | Rust | 38 | 8 | 3 small: [`get_key_value_mut`](https://github.com/indexmap-rs/indexmap/commit/cd4c1a53), [`split_at_checked`](https://github.com/indexmap-rs/indexmap/commit/61c9d534), [`Clone` for `IntoKeys`](https://github.com/indexmap-rs/indexmap/commit/88efd0ca) |
| [serde_json](https://github.com/serde-rs/json) | Rust | 16 | 12 | none ✅ |
| [FluentValidation](https://github.com/FluentValidation/FluentValidation) | C# | 9 | 5 | none ✅ |

Checked Oct 30-31, 2026 with `bite --free` on the last 40 commits that changed code (fewer when a project had fewer).
**Changes checked** counts only changes Bite could test. It leaves out tidy-ups, version bumps, code for another OS,
and old commits whose tests can't run any more with today's tools.

## What the unnoticed changes mostly were

- **Upkeep a test can't see:** lint fixes, renames, rewrites that work the same, speed-ups, support for old
  compilers removed. anyhow, indexmap and bytes are mostly this, so their "noticed" numbers are low, and that's fine.
- **Code for somewhere else:** shell scripts cobra writes for bash, fish and PowerShell, fixes for old browsers in
  object-inspect, and pointer fixes in bytes that only Rust's Miri checker can see.
- **A later test:** a few fixes had no test on the day, and one was added later (more-itertools, minimist, testify).

## Close calls

[pluggy 0b7790eb](https://github.com/pytest-dev/pluggy/commit/0b7790eb) fixed how hook argument names are read for
a function attached to a class. Its new test defined that function *inside* the test, which gave it a dotted name,
so on the day the old code already passed it: taking the fix out left the test green. Five days later
[dd20a85](https://github.com/pytest-dev/pluggy/commit/dd20a85) changed how those names are read, and today the
same test does fail without the fix. So it isn't counted as a gap, but it shows what Bite looks for: a test can
pass for the wrong reason.

Rechecking every gap against today's code found three more that tests now cover, so they aren't counted either:
[chi 878fe71f](https://github.com/go-chi/chi/commit/878fe71f) (a later change,
[7fcb8a2](https://github.com/go-chi/chi/commit/7fcb8a2), made its test work outside a terminal),
[bytes `try_unsplit`](https://github.com/tokio-rs/bytes/commit/804ee6d0) (an example in its docs tests it), and
[indexmap `VacantEntry::insert_sorted_by`](https://github.com/indexmap-rs/indexmap/commit/3dbb123c) (a test with
random inputs covers it).

## What the scoreboard taught Bite

Running Bite on 20 projects found bugs in Bite itself. They're fixed:

- [#74](https://github.com/connabyss/bite/pull/74): on JavaScript projects Bite made its copies in a hidden folder,
  and Express's tests refuse paths with a hidden folder in them. 60 of Express's tests failed in every copy.
- [#78](https://github.com/connabyss/bite/pull/78): Express has a passing test called "should persist store when
  parse error", and Bite read the words "parse error" as a failure.

Still to fix: in Rust, an example in the docs is also a test, and Bite takes the example out along with the code, so
it misses that the method was tested.

## Check it yourself

Every row can be rerun: `pipx install bite-check`, clone the project, then `bite --free --last 150 --free-checks 40`
inside it. You need the project's own test tools installed.
