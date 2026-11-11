# PWD Document Checker — User Guide

This guide explains how to use each part of the app and how to read what it
shows. Each tab has examples of good, normal and poor results.

The app looks at a picture of a document and checks two things:

1. **Is the picture clear enough?**
2. **Does any part of the page look changed?** If so, it shows *where*.

> **The app only helps you decide what to look at.** It cannot prove that a
> document is real or fake. A trained person always makes the final
> decision.

To start the app, see [README.md](README.md). Then open
<http://localhost:8501> in a browser.

---

## The screen at a glance

```text
┌──────────────┬──────────────────────────────────────────────────────┐
│  SIDEBAR     │  🔎 PWD Document Checker                              │
│              │                                                      │
│  Checker     │  [ 📄 Check a document ] [ 🧪 Forgery lab ] [ ⚙️ How it works ]
│  ● Ready     │                                                      │
│              │   Your page   Colour map    │ How clear is the picture? │
│  Warning     │   ┌───────┐   ┌───────┐     │ 81%  Good                 │
│  level       │   │       │   │  ▣    │     │                           │
│  ──────●     │   └───────┘   └───────┘     │ Change score              │
│              │   Spots to look at first    │ 70%  Nothing clear found… │
│  Colour      │                             │                           │
│  strength    │                             │                           │
└──────────────┴──────────────────────────────────────────────────────┘
```

| Tab | What it is for | When to use it |
| --- | --- | --- |
| 📄 **Check a document** | Check a real document | Every day |
| 🧪 **Forgery lab** | The app changes a page on purpose, then checks whether the checker finds the change | To learn what the checker can and can't find |
| ⚙️ **How it works** | How the checker was made, and what it can't do | Before you rely on a result |

---

## The sidebar (on every tab)

| You see | What it means |
| --- | --- |
| **Checker: Ready** (green) | The check for changes is working. If it says **Checker not set up yet** or **Checker could not start** (red), only the picture-clarity check works. |
| **File · trained · running on** | Which checker file is in use, and whether it runs on the computer's main processor (CPU) or a graphics card (GPU). |
| **Warning level** | The change score at which a page gets a red warning. The starting value is **0.995 (99.5%)**. It was chosen when the checker was tested. |
| **Colour strength on the map** | How strong the colours look on the colour map. It does not change any result. |

**Changing the warning level:**

- **Lower** (for example 0.980): finds more changes, but more real pages get
  a warning by mistake.
- **Higher**: fewer false warnings, but more changes are missed.
- Leave it as it is unless your team has agreed on a different value.

---

## Tab 1 — 📄 Check a document

### Step by step

1. **Upload a scan or photo of the document.** Drag the file onto the box,
   or click **Browse files**.
   - Accepted file types: PNG, JPG, WEBP, TIFF, BMP.
   - PDF is not accepted. Save the page as a picture first.
   - The largest file allowed is 25 MB.
2. **Wait a few seconds** while it shows *"Checking the page for changes …"*.
3. **On the right, read the two result boxes.**
4. **Not sure what a score means?** Click **ℹ️ What do these scores mean?**
   under the boxes. It explains each score using your page's own numbers,
   and it shows which band your page falls in.
5. **On the left, look at the pictures.**

### Right side: the two result boxes

#### Box 1 — "How clear is the picture?"

A percentage, a label, and four bars that show what makes up the score:

| Bar | Question it answers |
| --- | --- |
| **Sharpness** | Is the writing crisp, not blurry? |
| **Contrast** | Does the writing stand out clearly from the paper? |
| **Brightness** | Is the picture neither too dark nor too bright? |
| **Resolution** | Is the picture big enough to show small details? |

| Score | Label |
| --- | --- |
| 70% and above | 🟢 **Good — the picture is clear** |
| 40% to 69% | 🟡 **Acceptable — the picture can be used** |
| Below 40% | 🔴 **Poor — the picture is not clear enough**. A yellow message asks for a clearer scan or photo |

> **Always look at Box 1 first.** If the picture is poor, don't trust Box 2,
> even when it says "No signs of changes found".

#### Box 2 — "Change score (higher = more likely changed)"

A percentage, one of three messages, and a short note under it:

| Change score | Message | Note under it |
| --- | --- | --- |
| **99.5% or more** (the warning level) | 🔴 **⚠ Possible changes found — a person should check this page** | *Look at the boxed spots on the colour map. This is a warning, not proof.* |
| **About 70% up to the warning level** | 🟡 **Nothing clear found, but the score is close to the warning level** | *This is common for real pages. Look at the boxed spots only if something seems wrong.* |
| **Below about 70%** | 🟢 **✔ No signs of changes found** | *Some kinds of changes can still be missed.* |

> **The change score is not the chance that the document is fake.** It
> shows how unusual the *most unusual spot* on the page looks. A score of
> 90% does not mean "90% likely to be fake".
>
> **The yellow message is normal.** Most real pages score between 70% and
> 99%, so most real pages show yellow. Only **red** means the checker found
> something worth sending to a person. In our tests, about 1 real page in 14
> got a red warning by mistake.

### Left side: the pictures

| Picture | What it shows |
| --- | --- |
| **Your page** | Your page as the checker saw it. Big pages are made smaller first. |
| **Colour map** | Your page with colours on top. **Blue = looks normal. Yellow to red = may have been changed.** **Yellow boxes** mark spots to look at. |
| **Spots to look at first** | Zoomed-in views of up to three boxed spots, most likely first. Each one shows its score. |

Boxes can appear on real pages too. A box only means "look here". It does
not mean "changed".

### Examples

These are real results from this app on example forms.

#### ✅ Good — clear scan, real page

| Box | Result |
| --- | --- |
| How clear is the picture? | **78% — Good** (sharpness 83%, contrast 64%, brightness 62%, resolution 100%) |
| Change score | **69% — 🟢 ✔ No signs of changes found** |

**What to do:** nothing more. Carry on as normal.

#### 🟡 Normal — clear scan, real page, yellow message (most common)

| Box | Result |
| --- | --- |
| How clear is the picture? | **81% — Good** |
| Change score | **70% — 🟡 Nothing clear found, but the score is close to the warning level** |
| Colour map | Mostly blue, with a small warm spot and a box |

**What to do:**

1. Look at the zoomed spot.
2. If it's ordinary printed writing or a line with nothing odd, carry on as
   normal.
3. Yellow on its own is **not** a reason to reject a document.

#### 🔴 Warning — one value on the page was changed

The same form, but a date was replaced with a different one.

| Box | Result |
| --- | --- |
| How clear is the picture? | Acceptable |
| Change score | **99.8% — 🔴 ⚠ Possible changes found — a person should check this page** |
| Colour map | A red spot exactly on the changed date, with a box around it |

**What to do:**

1. Look closely at the boxed writing. Is the font, size or ink colour
   different? Is it sitting off its line? Is the paper behind it cleaner or
   more smudged?
2. Send the document to a person to check, and ask for the original if you
   can.

#### ❌ Poor — blurry scan

| Box | Result |
| --- | --- |
| How clear is the picture? | **32% — Poor** (sharpness 7%), with the message *"The picture is not clear enough. Please ask for a clearer scan or photo…"* |
| Change score | **66% — 🟢 ✔ No signs of changes found** |

**This green result can't be trusted.** Blur hides the signs of changes.
**What to do:** ask for a clearer scan, then check again.

### Tips for a good picture

- A scanner is better than a phone.
- With a phone, use good, even light, hold it flat above the page and avoid
  shadows.
- Upload the original file. Screenshots, and files sent many times over
  chat apps, lose detail.
- One page per picture.

---

## Tab 2 — 🧪 Forgery lab

With a real document, you never know for sure whether it was changed. In
the Forgery lab the app **changes a real page on purpose**, so we know
exactly what was changed. Then it checks whether the checker finds the
change. Use it to learn what the checker is good at and where it fails.

> **Before you start:** upload a page in **Check a document** first. The lab
> uses your last upload.

### Step by step

1. **Real page to change**: choose **"Your upload: (your file's name)"**.
2. **Type of change**: choose one of four:

   | Type of change | What the app does | Practised in training? |
   | --- | --- | --- |
   | **Replace writing** | Removes some writing in a field and puts different writing in its place | Yes |
   | **Copy within the page** | Copies a piece of writing to another place on the same page | Yes |
   | **Paste from another page** | Takes a piece of writing from a different page and pastes it onto this one | Yes |
   | **Erase writing (new to the checker)** | Wipes out some writing and fills the gap to look like blank paper | **No**. This tests a change the checker never practised on |

3. **🎲 Try a different change**: makes the same type of change in a
   different place. Press it a few times to see how results vary.
4. **Read the three boxes:**

   | Box | What you want to see |
   | --- | --- |
   | **Before the change (should be low)** | 🟢 or 🟡, with no warning on the real page |
   | **After the change (should be high)** | 🔴 ⚠ Possible changes found |
   | **Did it find the right spot? (0% = missed it, 100% = exactly right)** | Above about 50% is a good match |

   The bottom of the third box gives the overall result:
   - **✔ Change found, and the real page passed**: the checker got it right.
   - **✖ Change missed, or the real page got a warning**: it got it wrong.

   Click **ℹ️ What do these scores mean?** under the boxes for a plain
   explanation of each score.

5. **Look at the pictures** (close-up and whole page):
   - **Before**, the page without the change.
   - **After (green = what was changed)**, the truth.
   - **What the checker found**, the colour map.

   In a good result, the red on the colour map sits on the green outline.

If you see *"The app could not find suitable writing to change on this
page"*, choose another page or press 🎲.

### Forgery lab examples

These are from real runs on a clear medical form.

#### ✅ Good — change found in the right spot

**Replace writing.**

| Before the change | After the change | Right spot? | Result |
| --- | --- | --- | --- |
| 65% 🟢 | 100% 🔴 | **71%** | **✔ Change found, and the real page passed** |

#### 🟡 Normal — change found, but the spot is only roughly right

**Replace writing**, after pressing 🎲.

| Before the change | After the change | Right spot? | Result |
| --- | --- | --- | --- |
| 54% 🟢 | 99.9% 🔴 | **17%** | **✔ Change found, and the real page passed** |

The page got a warning, but the red only partly covers the green outline.
**Lesson:** when you check a red page, look **near** the boxes, not only
inside them.

#### ❌ Poor — change missed

**Copy within the page.**

| Before the change | After the change | Right spot? | Result |
| --- | --- | --- | --- |
| 65% 🟢 | 65% 🟢 | **0%** | **✖ Change missed, or the real page got a warning** |

The checker saw no difference at all.

### What the lab shows about this checker

We tried 9 changes of each type on three pages. The table shows how many
the checker found:

| Type of change | Found |
| --- | --- |
| Replace writing | **6 of 9** |
| Paste from another page | 2 of 9 |
| Copy within the page | 0 of 9 |
| Erase writing | 0 of 9 |

**In short:** the checker is best at finding **replaced writing**. It
usually misses **writing copied within the same page** and **erased
writing**. A green result does **not** prove that a page was never changed.

---

## Tab 3 — ⚙️ How it works

This tab only explains. Nothing here changes a result.

| Section | What it says |
| --- | --- |
| **How the checker was made** | Five steps in plain words: real pages to learn from, the picture-clarity rule, the practice changes, how the checker looks at the page's fine "grain", and how it was tested on pages it had never seen. |
| **How picture clarity is measured** | The four questions from Box 1, how much each one counts (sharpness 45%, contrast 25%, brightness 15%, resolution 15%), and the Poor / Acceptable / Good limits. |
| **Test results** | Numbers from the final test, each with a **?** you can hover over for an explanation. **This section doesn't appear with the current checker file**, because the file has no saved test results. It appears after the checker is retrained with the notebook. |
| **What the checker can't do** | The limits listed below. |

### What the checker can't do

- It practised only on **changes the app made itself**. Real fake documents
  may look different.
- **Unclear pictures hide changes.** Always check picture clarity first.
- **It misses many changes.** In the training notebook's final test, it
  found about **28%** of changed pages. On the same test, 98% of real pages
  passed without a warning.
- **About 1 real page in 14 gets a red warning by mistake.**
- It only helps you decide what to look at. **A trained person always makes
  the final decision.**

---

## Quick reference

| You see | What it means | What to do |
| --- | --- | --- |
| **Poor — the picture is not clear enough** | The picture is too blurry, faint, dark or small | Ask for a clearer scan. Don't trust the change score |
| 🟢 **✔ No signs of changes found** | Nothing stood out | Carry on as normal. Some changes can be missed |
| 🟡 **Nothing clear found, but the score is close to the warning level** | Normal for most real pages | Glance at the boxed spots. Act only if something looks wrong |
| 🔴 **⚠ Possible changes found — a person should check this page** | The score reached the warning level | Look at the boxed spots and send the document to a person |
| **Checker not set up yet** / **Checker could not start** | The check for changes is off | Only picture clarity is checked. See Troubleshooting in the README |
