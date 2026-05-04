# LanGear

LanGear is an English retelling training product centered on lesson-based speaking practice, feedback, and follow-up use. This context exists to keep the product language stable as training, dialogue, and card capabilities expand.

## Language

**Lesson**:
A teachable unit that groups the cards, feedback, and follow-up practice for one piece of study content.
_Avoid_: Deck, course section

**Card**:
The smallest practice item inside a **Lesson**, usually anchored to one sentence or expression.
_Avoid_: Question, line

**Study Session**:
A retelling practice session where the learner records against lesson cards and receives card-level feedback.
_Avoid_: Dialogue, chat session

**Dialogue Session**:
A scenario-based speaking session that helps the learner immediately use what they just studied after a **Study Session**.
_Avoid_: Study session, submission

**Scenario**:
A task-oriented conversation setup with fixed goals and roles but dynamically generated turns.
_Avoid_: Script, free chat

**Dialogue Goal**:
The concrete objective a learner must complete inside a **Dialogue Session**.
_Avoid_: Turn count, duration

**Dialogue Entry Point**:
The product entry path from which a learner starts a **Dialogue Session**.
_Avoid_: Trigger, redirect source

**Target Expressions**:
The lesson expressions a learner is expected to actively use during a **Dialogue Session**.
_Avoid_: Vocabulary list, optional phrases

**Dialogue Review**:
A session-level review that summarizes how well the learner completed the scenario and transferred lesson content into use.
_Avoid_: Single feedback, card feedback

**Dialogue Turn**:
One learner or agent utterance inside a **Dialogue Session**.
_Avoid_: Review unit, submission

## Relationships

- A **Lesson** contains one or more **Cards**
- A **Study Session** is anchored to exactly one **Lesson**
- A **Dialogue Session** is anchored to exactly one **Lesson**
- A **Dialogue Session** may follow a **Study Session**, but it is not part of the same session type
- A **Dialogue Session** is entered explicitly by the learner
- A **Dialogue Session** has exactly one **Dialogue Entry Point**
- A **Dialogue Session** runs inside exactly one **Scenario**
- A **Scenario** defines one or more **Dialogue Goals**
- A **Dialogue Session** may define zero or more **Target Expressions**
- A completed **Dialogue Session** produces one **Dialogue Review**
- A **Dialogue Session** contains one or more **Dialogue Turns**
- A **Dialogue Review** evaluates the **Dialogue Session** as a whole, not each **Dialogue Turn** independently in the first version
- A **Dialogue Review** checks how well **Target Expressions** were transferred into actual use
- The default **Dialogue Entry Point** in the first version is the explicit button shown after a learner completes all **Cards** in a **Lesson**

## Example dialogue

> **Dev:** "When the learner finishes retelling a lesson and enters scenario practice, are they still in the same **Study Session**?"
> **Domain expert:** "No — that becomes a **Dialogue Session** tied to the same **Lesson**, using the training result as context."
>
> **Dev:** "Do we mark the dialogue as done after six turns?"
> **Domain expert:** "No — a **Dialogue Session** is complete when its **Dialogue Goals** are completed, not when it reaches a fixed number of turns."
>
> **Dev:** "Should we review each **Dialogue Turn** separately?"
> **Domain expert:** "Not in the first version — we keep **Dialogue Turn** as a session component, but the formal review unit is still the whole **Dialogue Session**."
>
> **Dev:** "What keeps this from becoming free chat?"
> **Domain expert:** "A **Dialogue Session** is tied to a **Lesson**, entered from a defined **Dialogue Entry Point**, and may carry **Target Expressions** that must be used in the scenario."
>
> **Dev:** "When does the learner enter the **Dialogue Session**?"
> **Domain expert:** "In the first version, the learner enters it explicitly from a button shown after all **Cards** in the **Lesson** have been completed."

## Flagged ambiguities

- "对话练习" was ambiguous between a retelling flow and a scenario chat flow — resolved: retelling belongs to **Study Session**, scenario use belongs to **Dialogue Session**.
- "完成对话" was ambiguous between reaching enough turns and finishing the scenario — resolved: completion is based on **Dialogue Goals**, not turn count.
- "对话轮次" was ambiguous between a storage unit and a review unit — resolved: **Dialogue Turn** exists, but first-version review remains session-level.
- "场景难度" was considered as a possible concept, but rejected for the first version — resolved: first-version **Dialogue Session** has no domain-level difficulty model.
- "情境对话入口" could have meant any lesson-related page — resolved: the first-version default **Dialogue Entry Point** is the explicit post-lesson-completion button.
