
# NoteBridge
Collaborative Note Taking Platform for Inclusive Learning

## Overview
NoteBridge is a collaborative note-taking application designed to make learning more inclusive and accessible. It enables users to create, share, and manage notebooks and groups while providing voice commands and intelligent navigation features for enhanced accessibility.

## Features

- **User Authentication:** Secure login and logout system.
- **Notebooks Management:** Create, view, edit, and delete personal and shared notebooks.
- **Group Collaboration:** Create, view, edit, and delete groups, and manage group members.
- **Accessibility Features:**
  - **Voice Commands:** Control the dashboard using spoken commands.
  - **Text-to-Speech:** Read dashboard content, individual notebooks, and groups.
  - **Font Size Control:** Increase, decrease, or reset font size via voice or UI.
  - **High Contrast Mode:** Enable or disable high contrast for better visibility.
- **Search Functionality:** Search notebooks quickly via the search bar.
- **Responsive UI:** Modern and intuitive interface with sidebar navigation.

## Voice Commands

The following voice commands are supported:

| Command | Action |
|---------|--------|
| "read page" or "read dashboard" | Reads the full dashboard text aloud |
| "increase font" or "large text" | Sets font size to large |
| "decrease font" or "small text" | Sets font size to small |
| "normal font" | Resets font size to medium |
| "enable high contrast" | Turns on high contrast mode |
| "disable high contrast" | Turns off high contrast mode |
| "open notebook [number]" | Opens the specified notebook |
| "read notebook [number]" | Reads the content of the specified notebook |
| "logout" or "sign out" | Logs the user out |
| "help" | Announces available commands |


## Setup Instructions

1. Clone the repository:

```bash
git clone https://github.com/ReddySrujana/NoteBridge
cd NoteBridge
````

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the application:

```bash
python app.py
```

4. Open the app in a browser:

```
http://127.0.0.1:5000
```

5. Ensure you use **Chrome** for full voice recognition support.


## Notes

* Voice commands are powered by **Web Speech API** (Chrome required).
* The database `notebridge.db` stores all user, notebook, and group data.
