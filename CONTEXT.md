# LanGear

LanGear is an English speaking and spaced-repetition product. It uses Anki-style content and review concepts internally while keeping learner-facing language focused on practice, feedback, and later scenario use.

## Language

**Collection**:
The ownership and isolation boundary for one user's Decks, Notes, Cards, Attempts, and private media. The first version gives each user one Collection; the system Library is a separate read-only Collection.
_Avoid_: Database, Deck

**Deck**:
A review container that organizes Cards in a hierarchy and controls which Cards are selected for study. A Deck is not the underlying content record.
_Avoid_: Lesson when referring to a review container

**Lesson**:
A learner-facing label for a teachable slice of content, when the product needs to describe a textbook lesson. Internally, it is represented by a Deck or Deck subtree rather than a separate learning-lifecycle entity.
_Avoid_: Course completion unit, Study Session container

**Note**:
The editable content record that may render into zero or more Cards through a NoteType. A Note does not belong to a Deck; its generated Cards may be placed in different Decks.
_Avoid_: Card, Lesson

**NoteType**:
The schema for a Note: its fields, Card Templates, allowed input modes, and rendering rules. The first version provides Vocabulary and Sentence system NoteTypes.
_Avoid_: Lesson type, Deck type

**Card Template**:
A system-defined practice view that renders one Card from a Note and defines its prompt, answer, and allowed input modes.
_Avoid_: Note, question type

**Card**:
The smallest review/practice item, rendered from one Note through one Card Template and independently scheduled by FSRS.
_Avoid_: Question, line

**Sentence Retelling**:
A Sentence Card Template where the learner responds to a reference prompt with a required recording.
_Avoid_: Sentence Dictation, optional-audio practice

**Sentence Translation**:
A Sentence Card Template where the learner translates the Chinese prompt into required English text.
_Avoid_: Sentence Retelling, direct reveal

**Sentence Dictation**:
A Sentence Card Template where the learner listens to reference audio and enters required English text without submitting a learner recording.
_Avoid_: Sentence Retelling, silent Attempt

**Attempt**:
One submitted practice input created when the learner flips a Card. It stores the immutable practice snapshot and the independently completed ASR, AI feedback, and learner Rating results.
_Avoid_: Trial recording, Study Session

**Rating**:
The learner's Again, Hard, Good, or Easy choice that advances the Card's FSRS schedule. AI feedback does not silently choose a Rating.
_Avoid_: AI score, feedback score

**AI Feedback**:
Personalized guidance produced for one Attempt according to its Card Template's evaluation mode. It is independent from learner Rating and distinct from pre-authored Card content.
_Avoid_: Rating, AI Explanation, automatic grade

**Card Deletion**:
The irreversible permanent removal of exactly one rendered Card and its associated Attempts, without implicitly deleting its underlying Note or sibling Cards.
_Avoid_: Note deletion, recycle-bin removal, lesson cleanup

**Library**:
The read-only system Collection from which a learner copies Decks and Notes into their own Collection. Library imports become independently editable user content and do not auto-sync.
_Avoid_: Shared user Deck, course subscription

**Filtered Deck**:
A temporary review container that borrows Cards by moving them from their Standard Deck and storing enough original placement information to return them later.
_Avoid_: Permanent Card ownership, saved study history

**AI Explanation**:
A pre-authored, Card-level explanation that tells the learner how to understand and practice one sentence or expression. It is learning content, not personalized submission advice.
_Avoid_: AI Feedback, Chat answer, agent reply

**Study Session**:
A future learner-facing concept for a bounded practice flow. It is not required as a persistent container in the first version; the current review queue is runtime state.
_Avoid_: Dialogue Session, database queue

**Dialogue Session**:
A future scenario-based speaking session that helps the learner use recently studied language. It is distinct from Card review and Study Session.
_Avoid_: Study Session, free chat

**Scenario**:
A task-oriented conversation setup with fixed goals and roles but dynamically generated turns. A Scenario is generated once at Dialogue Session start and remains stable for that session.
_Avoid_: Script, free chat

**Dialogue Goal**:
The concrete objective a learner must complete inside a Dialogue Session.
_Avoid_: Turn count, duration

**Dialogue Entry Point**:
The explicit product path from which a learner starts a Dialogue Session. The first version defers this feature; it must not be inferred from a Card queue becoming empty.
_Avoid_: Automatic course completion

**Dialogue Review**:
A session-level review of how well a learner completed a Scenario and transferred Target Expressions into use.
_Avoid_: Card feedback, Attempt

**Target Expressions**:
The expressions a learner is expected to actively use during a Dialogue Session.
_Avoid_: Vocabulary list, optional phrases

**Dialogue Turn**:
One learner or agent utterance inside a Dialogue Session. In the first version, formal review remains session-level rather than turn-level.
_Avoid_: Review unit, submission

## Relationships

- A Collection owns Decks, Notes, Cards, Attempts, and private media.
- A Deck contains zero or more Cards and may have child Decks.
- A Note may render zero or more Cards.
- A Card belongs to exactly one Note, one Card Template, and one current Deck.
- A NoteType defines one or more Card Templates; valid templates generate persistent Cards by default.
- Vocabulary provides English-to-Chinese and Chinese-to-English Cards.
- Sentence provides Retelling, Translation, and Dictation Cards.
- A Card Deletion removes only that Card and its Attempts; it does not delete the Note or sibling Cards.
- A Note may remain in a Collection with no Cards and can later be used to explicitly generate missing Cards.
- A Dialogue Session is deferred; it will be anchored to a learner-facing Lesson/Deck slice, not to the current runtime review queue.

## Anki Alignment

- LanGear aligns storage and authoring with Anki's Deck, Note, NoteType, fields, templates, and rendered Card separation.
- Learner-facing language may use Lesson and Card; Anki terms are acceptable in authoring or implementation contexts.
- A Note has a stable `guid` for import identity. Library copies retain the Library guid for idempotent re-import; local edits are never overwritten by a repeat import.
- A Note has no Deck ownership. Cards generated from it may be moved independently and may be mixed with any NoteType in a Deck.
- All valid Card Templates generate Cards by default. Users can suspend or hard-delete individual Cards; normal page loads do not silently regenerate deleted Cards.
- FSRS state belongs to the user's Card copy. Attempts record practice facts; the current review queue is runtime state and may be rebuilt.

## AI Explanation Style

- Explain English sentences and expressions in Chinese.
- Start with practical meaning, then give a small number of useful language points and a short practice summary.
- Keep the explanation tied to the Card; do not turn it into open-ended tutoring or a persistent chat thread.

## Flagged Ambiguities

- "课程" was ambiguous between a learning lifecycle and a review container — resolved: the first version uses hierarchical Decks and has no permanent course-completion concept.
- "Study Session" was ambiguous between a persistent session record and a runtime review queue — resolved: the first version does not persist a Study Session container.
- "复习记录" was ambiguous between a practice submission and an FSRS transition — resolved: one Attempt is created on Card flip; its Rating is a separate field on the same Attempt.
- "试录" was ambiguous between a persisted practice event and temporary input — resolved: pre-flip recordings are temporary; only the recording submitted on flip becomes Attempt input.
- "不录音听音频" was ambiguous with a silent Retelling Attempt — resolved: it is Sentence Dictation, while Sentence Retelling requires a learner recording before flip.
- "Translation 输入" was ambiguous between optional reflection and a submitted answer — resolved: Sentence Translation requires English text before flip and does not accept learner audio.
- "Library 导入" was ambiguous between shared references and copies — resolved: Library Decks and Notes are copied into the user's Collection; copied Notes retain the Library guid for idempotent re-import, but local edits are never overwritten.
- "删除卡片" was ambiguous between deleting one rendered Card and deleting its Note — resolved: Card Deletion removes only one Card and its Attempts.
- "对话练习" was ambiguous between retelling and scenario use — resolved: retelling belongs to Card review; scenario use belongs to Dialogue Session, which is deferred.
