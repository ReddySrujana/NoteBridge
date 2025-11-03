document.addEventListener('DOMContentLoaded', async () => {

  // ==============================
  // INITIALIZATION
  // ==============================
  const socket = io();
  const noteId = window.noteData.noteId;
  const notebookId = window.noteData.notebookId;
  const noteTitle = window.noteData.noteTitle;
  const dashboardUrl = window.noteData.dashboardUrl;
  const logoutUrl = window.noteData.logoutUrl;

  const editor = document.getElementById('editor');
  const noteContent = document.getElementById('note-content');
  const saveBtn = document.getElementById('save-btn');
  const deleteBtn = document.getElementById('delete-note-btn');
  const readBtn = document.getElementById('read-page-btn');
  const clearBtn = document.getElementById('clear-btn');
  const stopVoiceBtn = document.getElementById('stop-voice-btn');
  const dictateBtn = document.getElementById('dictate-btn');
  const synth = window.speechSynthesis;

  socket.emit('join_note', { note_id: noteId });

  // ==============================
  // SPEECH SYNTHESIS
  // ==============================
  // Global speech function
  function speak(text) {
    if (!window.speechSynthesis) {
      console.warn("Speech synthesis not supported in this browser.");
      return;
    }

    window.speechSynthesis.cancel(); // Stop any ongoing speech
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    utterance.pitch = 1;
    utterance.rate = 1;
    utterance.volume = 1;
    window.speechSynthesis.speak(utterance);
  }
  // === STOP SPEECH ON PAGE UNLOAD OR REFRESH ===
  window.addEventListener("beforeunload", () => {
    window.speechSynthesis.cancel(); // stop any ongoing speech
  });


  async function logContribution(action, detail = '') {
    await fetch('/log_contribution', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note_id: noteId, action, detail })
    });
  }

  // ==============================
  // DICTATION FEATURE
  // ==============================
  let dictationActive = false;
  let dictationRecognition;

  dictateBtn.addEventListener('click', () => {
    if (dictationActive && dictationRecognition) {
      dictationRecognition.stop();
      dictationActive = false;
      dictateBtn.textContent = "Start Dictation";
      speak("Dictation stopped.");
      return;
    }

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      speak("Speech recognition not supported in this browser.");
      return;
    }

    dictationRecognition = new SpeechRecognition();
    dictationRecognition.lang = 'en-US';
    dictationRecognition.continuous = true;

    dictationRecognition.onresult = (event) => {
      const transcript = event.results[event.results.length - 1][0].transcript;
      editor.value += (editor.value ? " " : "") + transcript;
    };

    dictationRecognition.onerror = () => speak("Dictation error occurred.");
    dictationRecognition.onend = () => {
      dictationActive = false;
      dictateBtn.textContent = "Start Dictation";
    };

    dictationRecognition.start();
    dictationActive = true;
    dictateBtn.textContent = "Stop Dictation";
    speak("Dictation started. You can start speaking.");
  });

  // ==============================
  // NOTE ACTIONS (SAVE / DELETE / READ / CLEAR)
  // ==============================
  saveBtn.addEventListener('click', async () => {
    const content = editor.value;
    const res = await fetch(`/note/${noteId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: noteTitle, content })
    });
    if (res.ok) {
      noteContent.innerHTML = `<pre>${content}</pre>`;
      socket.emit('edit', { note_id: noteId, content });
      speak("Note saved.");
      logContribution("save", "Updated note content.");
    }
  });

  deleteBtn.addEventListener('click', async () => {
    if (!confirm("Delete this note?")) return;
    const res = await fetch(`/note/${noteId}`, { method: 'DELETE' });
    if (res.ok) {
      logContribution("delete", "Note deleted.");
      speak("Note deleted.");
      window.location.href = `/notebook/${notebookId}`;
    }
  });

  readBtn.addEventListener('click', () => {
    let text = '';
    const title = document.querySelector('h1')?.innerText;
    if (title) text += `Title: ${title}. `;
    const content = editor?.value || noteContent.querySelector('pre')?.innerText;
    if (content) text += `Content: ${content}. `;
    const tags = [...document.querySelectorAll('.tag')].map(t => t.innerText).join(', ');
    if (tags) text += `Tags: ${tags}. `;
    const comments = [...document.querySelectorAll('.comment')].map((c, i) => {
      const username = c.querySelector('strong')?.innerText || 'Anonymous';
      const commentText = c.querySelector('.comment-text')?.innerText || '';
      return `Comment ${i + 1} by ${username}: ${commentText}`;
    }).join('. ');
    if (comments) text += `Comments: ${comments}.`;
    speak(text || "This page is empty.");
  });

  clearBtn.addEventListener('click', () => {
    editor.value = '';
    speak("Editor cleared.");
  });

  // ==============================
  // TAG MANAGEMENT
  // ==============================
  document.getElementById('add-tag-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const tag = document.getElementById('new-tag').value.trim();
    if (!tag) return;
    const res = await fetch(`/note/${noteId}/add_tag`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tag })
    });
    if (res.ok) {
      const tagList = document.getElementById('tag-list');
      const span = document.createElement('span');
      span.className = 'tag';
      span.textContent = tag;
      tagList.appendChild(span);
      document.getElementById('new-tag').value = '';
      speak(`Tag ${tag} added.`);
      logContribution("tag", `Added tag: ${tag}`);
    }
  });

  // ==============================
  // COMMENT SYSTEM
  // ==============================
  const commentSection = document.getElementById('comment-section');
  const commentForm = document.getElementById('comment-form');
  const commentInput = document.getElementById('comment-text');

  commentForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = commentInput.value.trim();
    if (!text) return;

    const res = await fetch(`/note/${noteId}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: text })
    });

    if (res.ok) {
      const div = document.createElement('div');
      div.className = 'comment';
      div.innerHTML = `<strong>You:</strong><p class="comment-text">${text}</p><small>Just now</small>`;
      commentSection.prepend(div);
      commentInput.value = '';
      speak("Comment added.");
      logContribution("comment", "Added a comment.");
    }
  });

  commentSection.addEventListener('click', async (e) => {
    const commentDiv = e.target.closest('.comment');
    if (!commentDiv) return;
    const commentId = commentDiv.dataset.id;

    if (e.target.classList.contains('reply-btn')) {
      const replyBox = document.createElement('textarea');
      replyBox.placeholder = 'Write a reply...';
      const replyBtn = document.createElement('button');
      replyBtn.textContent = 'Post Reply';
      replyBtn.className = 'btn';
      commentDiv.append(replyBox, replyBtn);

      replyBtn.addEventListener('click', async () => {
        const replyText = replyBox.value.trim();
        if (!replyText) return;

        const res = await fetch(`/note/${noteId}/comments`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: replyText, parent_id: commentId })
        });

        if (res.ok) {
          const replyDiv = document.createElement('div');
          replyDiv.className = 'comment reply';
          replyDiv.innerHTML = `<strong>You:</strong><p>${replyText}</p><small>Just now</small>`;
          commentDiv.append(replyDiv);
          replyBox.remove();
          replyBtn.remove();
          speak("Reply posted.");
          logContribution("reply", "Added a reply.");
        }
      });
    }

    if (e.target.classList.contains('edit-btn')) {
      const oldText = commentDiv.querySelector('.comment-text').textContent;
      const newText = prompt('Edit your comment:', oldText);
      if (newText && newText !== oldText) {
        const res = await fetch(`/comment/${commentId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: newText })
        });
        if (res.ok) {
          commentDiv.querySelector('.comment-text').textContent = newText;
          speak("Comment edited.");
          logContribution("edit_comment", "Edited a comment.");
        }
      }
    }

    if (e.target.classList.contains('delete-btn')) {
      if (!confirm("Delete this comment?")) return;
      const res = await fetch(`/comment/${commentId}`, { method: 'DELETE' });
      if (res.ok) {
        commentDiv.remove();
        speak("Comment deleted.");
        logContribution("delete_comment", "Deleted a comment.");
      }
    }
  });

  // ==============================
  // AUDIO CONTROLS
  // ==============================
  const audio = document.getElementById('audio-player');
  const playBtn = document.getElementById('play-btn');
  const pauseBtn = document.getElementById('pause-btn');
  const stopBtn = document.getElementById('stop-btn');
  const rewindBtn = document.getElementById('rewind-btn');
  const speedSelect = document.getElementById('speed-control');

  function beep() {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator();
    osc.type = 'square';
    osc.frequency.setValueAtTime(600, ctx.currentTime);
    osc.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.05);
  }

  function haptic() { if (navigator.vibrate) navigator.vibrate(30); }
  function feedback() { beep(); haptic(); }

  playBtn.addEventListener('click', () => { audio.play(); feedback(); speak("Audio playing."); });
  pauseBtn.addEventListener('click', () => { audio.pause(); feedback(); speak("Audio paused."); });
  stopBtn.addEventListener('click', () => { audio.pause(); audio.currentTime = 0; feedback(); speak("Audio stopped."); });
  rewindBtn.addEventListener('click', () => { audio.currentTime = Math.max(0, audio.currentTime - 10); feedback(); speak("Rewind 10 seconds."); });
  speedSelect.addEventListener('change', () => {
    audio.playbackRate = parseFloat(speedSelect.value);
    feedback();
    speak(`Playback speed set to ${speedSelect.value}x`);
  });




  //=------------------------------------------------------------//

  // ==============================
  // VOICE COMMANDS + SUMMARIZATION (FULL)
  // ==============================
  if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const assistant = new SpeechRecognition();
    assistant.continuous = true;
    assistant.interimResults = false;
    assistant.lang = 'en-US';

    let listening = false;
    let currentUtterance = null;

    // === MICROPHONE CONTROL ===
    function pauseListening() {
      try {
        assistant.abort();
        listening = false;
        console.log("⏸ Voice recognition paused during TTS playback.");
      } catch (err) {
        console.warn("pauseListening error:", err);
      }
    }

    function resumeListening() {
      try {
        if (!listening) {
          assistant.start();
          listening = true;
          console.log("▶️ Voice recognition resumed after TTS playback.");
        }
      } catch (err) {
        console.warn("resumeListening error:", err);
      }
    }

    // === SPEECH UTILITIES ===
    function speak(text) {
      stopSpeaking();
      pauseListening();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'en-US';
      utterance.rate = 1;
      utterance.pitch = 1;
      currentUtterance = utterance;

      utterance.onend = () => {
        console.log("🗣 Finished speaking TTS.");
        resumeListening();
      };
      utterance.onerror = (e) => {
        console.error("⚠️ Speech synthesis error:", e);
        resumeListening();
      };

      speechSynthesis.speak(utterance);
    }

    function stopSpeaking() {
      if (window.speechSynthesis.speaking || window.speechSynthesis.pending) {
        window.speechSynthesis.cancel();
      }
      currentUtterance = null;
    }

    // === MAIN VOICE RESULT HANDLER ===
    assistant.onresult = async function (event) {
      if (!event.results || event.results.length === 0) return;

      const transcript = Array.from(event.results)
        .map(r => r[0].transcript.toLowerCase().trim())
        .join(' ');

      const normalize = (t) => t
        .replace(/summarise|summerize|summary|summery/gi, "summarize")
        .replace(/note\s?book|not book|noot book|note buck/gi, "notebook")
        .trim();

      const command = normalize(transcript);
      console.log("🎤 Voice Command Heard:", command);

      // === HELP ===
      if (/\bhelp\b/.test(command)) {
        speak("Available commands include: save note, summarize notebook, read summary, dashboard, and logout.");
        return;
      }

      // === READ PAGE ===
      if (command.includes("read page")) {
        console.log("📖 Reading page content...");
        pauseListening();
        readBtn.click(); // triggers the readBtn click handler
        resumeListening();
        return;
      }


      // === SUMMARIZE NOTEBOOK ===
      if (command.match(/summarize notebook/)) {
        console.log("🧠 Fetching notebook summary...");
        pauseListening();
        try {
          const res = await fetch(`/notebook/${notebookId}/summarize`);
          const data = await res.json();
          const summary = data.summary || "No summary available.";

          // Remove old popup
          document.querySelectorAll("#summary-popup").forEach(p => p.remove());

          // Create popup
          const popup = document.createElement("div");
          popup.id = "summary-popup";
          popup.style = `
          position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
          background: #fff; color: #000; border: 2px solid #444; padding: 20px;
          border-radius: 12px; box-shadow: 0 0 15px rgba(0,0,0,0.3); z-index: 9999;
          max-width: 420px; text-align: left; overflow-wrap: break-word;
        `;
          popup.innerHTML = `<h3>📘 Notebook Summary</h3>
                           <p id="summary-text">${summary}</p>`;
          document.body.appendChild(popup);
          console.log("✅ Summary popup created.");
          speak("Notebook summary ready.");
        } catch (err) {
          console.error("Summary fetch failed:", err);
          speak("Failed to summarize the notebook.");
        } finally {
          resumeListening();
        }
        return;
      }

      // === GO BACK ===
      if (command.includes("go back")) {
        console.log("Voice command: Go Back");
        speak("Going back to the previous page.");
        window.history.back();
        return;
      }

      // === DASHBOARD ===
      if (command.includes("dashboard")) {
        console.log("Voice command: Go to Dashboard");
        speak("Navigating to dashboard.");
        window.location.href = dashboardUrl;  
        return;
      }



      // === READ SUMMARY (play summary.mp3 directly) ===
      if (command.match(/read summary|read summarize/)) {
        console.log("🔊 Playing saved summary audio...");
        pauseListening();

        // Reset previous audio if any
        if (window.currentSummaryAudio) {
          try {
            window.currentSummaryAudio.pause();
            window.currentSummaryAudio.currentTime = 0;
          } catch (e) {
            console.warn("⚠️ Could not reset previous audio:", e);
          }
          window.currentSummaryAudio = null;
        }

        try {
          const audioUrl = `/notebook/${notebookId}/summary.mp3?ts=${Date.now()}`;
          const audioPlayer = new Audio(audioUrl);
          audioPlayer.autoplay = true;
          window.currentSummaryAudio = audioPlayer;

          audioPlayer.onplay = () => console.log("▶️ Summary audio started playing.");
          audioPlayer.onended = () => {
            console.log("✅ Finished playing summary audio.");
            window.currentSummaryAudio = null;
            resumeListening();
          };
          audioPlayer.onerror = async (e) => {
            console.error("Audio playback error:", e);
            window.currentSummaryAudio = null;
            resumeListening();
            try {
              const check = await fetch(`/notebook/${notebookId}/summary.mp3`);
              if (check.status === 404) speak("Summary audio not found. Please generate it first.");
              else speak("Unable to play summary audio.");
            } catch {
              speak("Playback error or missing file.");
            }
          };
        } catch (err) {
          console.error("Error playing summary audio:", err);
          resumeListening();
          speak("Could not play the summary audio.");
        }
        return;
      }
    };

    // === KEEP RECOGNITION RUNNING ===
    assistant.onend = function () {
      if (listening) {
        console.log("🎙 Restarting recognition after normal end...");
        assistant.start();
      } else {
        console.log("🛑 Recognition intentionally paused.");
      }
    };

    assistant.onerror = function (e) {
      console.error("Speech recognition error:", e);
      if (listening) {
        try {
          assistant.start();
        } catch (err) {
          console.warn("⚠️ Could not restart recognition:", err);
        }
      }
    };

    // === START LISTENING INITIALLY ===
    assistant.start();
    listening = true;
    console.log("🎙 Voice recognition activated and ready.");
  }


  //=============================================================================//
  // === ADD COMMENT ===
  if (command.match(/^(add|post)( a)? comment/)) {
    pauseListening();
    const commentText = command.replace(/^(add|post)( a)? comment/, "").trim();
    if (!commentText) {
      speak("Please say your comment after 'add comment'.");
      resumeListening();
      return;
    }

    try {
      const res = await fetch(`/note/${noteId}/comments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: commentText })
      });
      if (res.ok) {
        speak("Comment added.");
      } else {
        speak("Failed to add comment.");
      }
    } catch (err) {
      console.error("Error adding comment:", err);
      speak("Error adding comment.");
    } finally {
      resumeListening();
    }
    return;
  }

  // === DELETE COMMENT ===
  if (command.match(/delete( a)? comment/)) {
    pauseListening();
    const numWordMatch = command.match(/delete( a)? comment ([\w-]+)/);
    if (!numWordMatch || !numWordMatch[2]) {
      speak("Please specify which comment number to delete.");
      resumeListening();
      return;
    }

    const num = wordToNumber(numWordMatch[2]);
    if (!num || isNaN(num)) {
      speak("Couldn't identify comment number.");
      resumeListening();
      return;
    }

    const commentDivs = [...document.querySelectorAll(".comment")];
    const target = commentDivs[num - 1];
    if (!target || !target.dataset.id) {
      speak(`Couldn't find comment ${num}.`);
      resumeListening();
      return;
    }

    try {
      const res = await fetch(`/comment/${target.dataset.id}`, { method: "DELETE" });
      if (res.ok) {
        target.remove();
        speak(`Comment ${num} deleted.`);
      } else {
        speak("Failed to delete comment.");
      }
    } catch (err) {
      console.error("Error deleting comment:", err);
      speak("Error deleting comment.");
    } finally {
      resumeListening();
    }
    return;
  }

  // logout command
  if (command.includes("logout") || command.includes("log out")) {
    stopSpeaking();
    speak("Logging out now.");
    window.location.href = logoutUrl;
    return;
  }

  // === STOP VOICE ===
  if (command.includes("stop voice") || command.includes("stop speaking")) {
    listening = false;
    stopSpeaking();
    assistant.stop();
    console.log("🛑 Voice assistant stopped.");
    speak("Voice control stopped.");
    return;
  }

  // === DEFAULT (DICTATION MODE) ===
  if (typeof editor !== "undefined" && editor) {
    editor.value += " " + transcript;
  } else {
    console.log("📝 No editor found for dictation.");
  }
});
