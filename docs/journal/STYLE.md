# Technical notes — style and standards

These notes exist to make quantum optimization **comprehensible and checkable**
to scientists, engineers, and technical leaders evaluating the field. They are
not a development diary and they are not marketing.

A sibling project in this lab keeps a build journal written as a
behind-the-scenes narrative for practitioners. This series is deliberately a
different instrument. Do not import that voice.

## What a reader should get

Someone who reads a note should be able to (a) explain the concept to a
colleague, (b) reproduce or check the numbers, and (c) tell precisely where the
boundary of our claim sits. If a note fails any of those three, it is not ready.

## Voice

**Authoritative, precise, explanatory.** The register of a good applied-research
note or an internal technical report — a senior engineer explaining something
they have actually measured to a smart colleague from an adjacent field.

- **Explain, then be precise.** Give the plain-language mechanism first, then
  the exact statement. Not one or the other. "The cost step rotates each
  candidate's phase in proportion to how bad it is" earns the right to then
  write exp(-i gamma H_C).
- **Define every term on first use, in every note.** Qubit, superposition,
  ansatz, density matrix, barren plateau, QUBO. The reader is senior and
  numerate but may have never written a circuit. Do not make them assemble
  meaning across notes.
- **Mathematics is welcome where it clarifies and banned where it decorates.**
  If an equation replaces three paragraphs, use it. If it only signals rigour,
  cut it. Always state what the symbols are.
- **Numbers carry provenance.** Every figure is one of: measured (say on what,
  when), computed from first principles (show the arithmetic), or cited (link
  it). A number without provenance does not go in.
- **Do not narrate the process.** "We tried X, then Y, then discovered Z" is the
  wrong shape. State the finding, then explain the mechanism that produces it.
  Our own errors appear when they teach something general — framed as the
  finding, not as autobiography.
- **First person plural, sparingly.** "We measured" is fine. "I spent an
  afternoon confused" is not.

## Structure

Each note answers one question, named in the title. Recommended shape:

1. **The question**, and why it matters to someone deciding anything.
2. **The concept**, plainly — analogy permitted as an on-ramp, never as the
   whole explanation.
3. **The mechanism** — the actual thing that happens, precisely.
4. **Worked example** — our measured numbers, with the configuration stated.
5. **What follows** — for algorithm design, for infrastructure, or for
   evaluating vendor claims.
6. **Limits of this note** — what we did not test, what remains contested.

## Accuracy standards

This field has active research disputes and a great deal of vendor noise. These
notes will be read by people who know the literature.

- **Distinguish proved, measured, and expected.** Never let the reader guess
  which one they are reading.
- **Name the contested claims and who contests them.** If tensor-network methods
  undercut a statement about statevector limits, say so in the note that makes
  the statement, not in a later correction.
- **State the model's boundary explicitly.** A DC power flow is not an AC
  solution. Depolarizing noise is not a calibrated device model. Say it where
  the result is presented.
- **Corrections are first-class.** When a claim here was wrong, the corrected
  note explains the error and why it was plausible. That is instructive; a
  silent edit is not.
- **A superseded implementation is not a wrong claim.** These are different
  things and the rule above covers only the first. A measurement that was wrong
  stays on the page with its correction, because how it was wrong is the
  lesson. A design that has simply been replaced does NOT: rewrite the note to
  describe what the system does now, and keep from the old version only what
  taught something general — framed as a finding, per the voice rules.
  Conflating the two produces a note that opens by telling the reader it is out
  of date, which serves the archive and not the reader. If a note cannot be
  understood without knowing what it used to say, it needs rewriting, not a
  banner.
- **Correct what we published; do not confess what we merely believed.** The
  test is whether a reader could have carried the wrong idea away. A claim that
  shipped gets its correction, because someone may be acting on it. A working
  assumption that never left our own sizing gets no mention at all — just state
  the fact. Writing "we believed X, and X is false" plants X in a reader who
  never had it, and spends their trust in the surrounding numbers to do so.

## Conventions

- **No emojis.** Anywhere.
- **SI units and standard notation.** MW, MVA, kV, Hz. Qubit counts as n.
- **Code and config in fenced blocks**, with the file path.
- **Pull-quote the sentence worth remembering**, at most one per note, using
  `!!! quote ""`.
- **References at the end**, each with one line on what it supports.

## Frontmatter

```yaml
---
id: note-NN-short-slug
type: note | implementation
title: "The question the note answers"
date: YYYY-MM-DD
audience: [scientist, engineer, leader]
tags: [qaoa, parameter-landscape, noise, memory-wall, qubo, power-flow]
prerequisites: "What a reader should already know, in one line. 'None' is a valid answer."
one_line: "The finding, compressed to a paragraph."
---
```
