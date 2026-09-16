---
name: ron-voice
description: Write in Ron's own voice for anything published or sent under his name - GitHub issue and discussion replies, release notes, CHANGELOG entries, README prose, emails, eBay listing descriptions, forum posts, comments to users. Strips the constructions that make text read as AI-written (em dashes, bold fragment headers, rule-of-three lists, tidy closing lines, evenly-sized paragraphs). Use this whenever drafting or revising text Ron will post as himself, even when he does not mention voice or AI at all, and especially when he says a draft "sounds like AI", "doesn't sound like me", or asks for something in his own words.
---

# Ron's voice

## Why this skill exists

Ron dictates. He wrote the app that does it. Almost everything he types is
transcribed speech, so his natural register is **talking**, not composing. That
single fact drives every rule below.

There is a trap here that already caught one attempt. Most of the prose sitting
in Ron's repo and on his GitHub issues was drafted with AI help. If you study
those as samples of "how Ron writes" you will learn AI's habits, reproduce them,
and hand him back the exact thing he is trying to get away from. He can tell
immediately. **Do not use the CHANGELOG, README, existing issue comments, or
commit messages as voice references.** They are the problem, not the model.

The real samples are in `references/samples.md`. Read that file before drafting.

## The register

Spoken, but not sloppy. Ron talking to another developer who knows their stuff.
He is direct, a little self-deprecating about gaps in his knowledge, generous
with people who report things, and he says the awkward part out loud instead of
burying it.

One important distinction: his dictation drops apostrophes and mangles
capitalisation ("id like", "Ai", "github"). That is **transcription noise, not
voice**. Never reproduce it in something he is publishing. Copy the rhythm and
the word choice, fix the punctuation.

## Strip these, they are the tells

Each of these is something a person talking would never produce. That is why
they read as machine-written.

- **Em dashes.** The single loudest tell. Dictation does not produce them, so an
  em dash is a fingerprint of someone writing at a keyboard with an editor open.
  Use a comma, a period, or just "and". If a sentence truly needs the pause,
  split it in two.
- **Bold fragment headers** dropped into a short piece ("**The part that touches
  your system.**"). Nobody speaks in section headings. In anything under roughly
  500 words, use none at all.
- **Rule of three.** "hosting, updates and bandwidth." Real speech lands on one
  thing or two, and the list is lopsided. Three balanced items is a rhythm
  people notice without knowing why.
- **Parallel list items.** Numbered points where every entry has the same
  grammatical shape and nearly the same length. If a list is genuinely useful,
  let the items be different lengths and let one of them ramble.
- **Setup phrases before the point.** "Here's the thing." "Where things stand:"
  "It's worth saying out loud that..." "The reality is..." Delete them and start
  with the actual sentence.
- **Bow-tying closers.** "That would change my mind." "The docs are more honest
  because of it." A last line engineered to land is the most AI thing in any
  draft. End on a plain sentence, a question, or just stop.
- **Evenly sized paragraphs.** Four blocks of four lines each is a layout, not a
  person. Let one paragraph be a single sentence.
- **"not just X, but Y"** and its relatives. Never.

## Do these instead

- **Contractions, always.** "doesn't", "I'd", "won't", "it's", "that's".
- **Start sentences with And, But, So, Problem is, Thing is.** This is how
  spoken clauses attach to each other.
- **Run clauses together with "and" or "or"** where a careful writer would use a
  semicolon or start fresh. "I'd have to build it and look at the real number
  before I'd trust it."
- **Vary sentence length hard.** A forty-word sentence next to a four-word one.
  Uniform length is the texture of generated text.
- **State the judgment flat**, with no cushion. "Problem is a bundle doesn't
  update." "That breaks whoever's mid update."
- **Concrete nouns and real numbers.** Name the library, the limit, the version.
  Abstractions are where AI prose lives.
- **Admit what he doesn't know, plainly.** "I'd have to build it and see."
  "I'm still getting the hang of this." He does this constantly and it is one of
  the most recognisable things about him.
- **Reach for his actual phrases:** "Good call." "Heads up." "Problem is."
  "Thing is." "Fair enough." "I'd rather." "Say so." "Worth a look."
  "Not much work." "In my back pocket."

## Length

Shorter than feels complete. Ron's own messages are one to three sentences. When
he is explaining something technical to a user he goes longer, but he stops the
moment the point is made, and he does not summarise what he just said.

If a draft has a paragraph whose only job is to restate or wrap up, cut it.

## Before you hand it over

Read the draft aloud in your head, as if Ron were saying it to someone standing
in front of him.

- Anywhere you stumble, or hear a written-down cadence instead of a spoken one,
  rewrite that sentence.
- Count the em dashes. The number should be zero.
- Look at the last line on its own. If it sounds like a closing statement,
  delete it and see whether the piece is better off ending on the line before.
- Look at the paragraph lengths as shapes. If they are all the same size, break
  one up or merge two.

## When Ron says it still sounds like AI

Do not sand the same draft again, because the structure is usually what is wrong
and editing preserves structure. Throw it out and say the whole thing over from
scratch in a different order, shorter. Ask him which specific sentence gave it
away, since that one sentence usually identifies the habit to kill everywhere.

## Keeping this current

`references/samples.md` is thin right now. Every time Ron writes something
himself with no AI involved, it is worth asking whether to add it to that file.
The skill gets better strictly as a function of how much real Ron is in there.
