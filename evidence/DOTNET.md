# Bite on .NET (C#), 2026-10-28

Asked for by a C#/Unity team that read the kit. What changed: Bite now guesses `dotnet test` (one .sln, or the one
test project), runs a claim test with `--filter "FullyQualifiedName~BiteClaim"` instead of a file path, treats
"no test matches the filter" as a test that never ran (not a pass), counts C# build errors as load failures, and
puts real Git LFS files back into its copies (git archive writes them as pointers).

Live run, real .NET 8 SDK + xUnit, $0 (the worker and the second check were scripted, so no key was used):
a small C# solution with a Claude commit "Fix Clamp so values stay between lo and hi" that only fixed the low
end. Bite guessed `dotnet test Calc.sln`, found the change unguarded, ran the claim test at the commit and on
today's code, and reported:

    FALSE "DONE": commit 9a24034e said "Fix Clamp so values stay between lo and hi".
      Calc.Tests.BiteClaimTests.HighEndIsClamped [FAIL]  Expected: 9  Actual: 50
      Today's code: STILL BROKEN.     (39s)

The old kit on the same repo: "no test command found".

Same repo, a second Claude commit that claims nothing ("Double, for the hangar view") and adds a C# test that
doesn't touch the new code. `--free --last 1`, 15s, $0:

    No fix claims found in the last 1 commits ... Checking the 1 that added tests
    TEST GUARDS NOTHING: 6e11091b "Double, for the hangar view": its own tests
      (tests/Calc.Tests/DoubleTests.cs) still pass with its code change taken out.

Limit: a test that calls the new code won't compile once the code is taken out, so it counts as guarded.

Not yet tried: a real model writing the C# test, a real public C# repo, and Unity projects (their tests run in the
Unity editor; set test_command to Unity's -batchmode -runTests yourself).

## Trial on two real public C# repos (2026-10-28, free pass only, $0)

Picked from a web search for C# repos with Claude-made commits and xUnit tests; run in a Docker box with no
network. Both have Claude commits that describe what was built and claim no fix (like most game repos).

- **Moonhollow-ops/Magischool-Game** (Godot game; the sim has its own test project). Settings:
  `test_command = dotnet test sim/Magischool.Sim.Tests`, `test_covers = sim/*`. Bite said no fix claims, checked
  the commits that added tests, printed each result as it came (6 checks, 24 min), and flagged one:
  3cbc1166 "Use 0.5 m tiles": its tests were rewritten to derive masses from the tile-size constant, so they
  still pass with the tile size back at 1 m; no test pins 0.5 m. A blind reviewer called it USEFUL (small).
- **nathhunt/CutoutEqD** (WinForms app + a Core library). `test_covers = src/CutoutEqD.Core/*, tests/*`: the 4 UI
  commits were listed as outside the tests' reach.

The trial found three Bite bugs, fixed with a self-check each: C# test files (FooTests.cs, *.Tests/) weren't
seen as tests; a `dotnet test` that ran no tests (the project had a hand-written test .exe then) counted as a
pass, giving 2 false "TEST GUARDS NOTHING"; and a comment-only edit was checked as a code change (blind
reviewer: NOISE). After the fixes those three are "no tests ran at this commit" or not checked.
