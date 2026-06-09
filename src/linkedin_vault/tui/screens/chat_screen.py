"""Chat screen — agentic RAG chat against the user's saved posts vault."""

from __future__ import annotations

from collections.abc import Iterable
from typing import ClassVar

from textual import events, work
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Input, RichLog, Static

from linkedin_vault.tui.vault_screen import VaultScreen

_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class HistoryInput(Input):
    """Input subclass that intercepts Up/Down for session-history navigation."""

    async def _on_key(self, event: events.Key) -> None:
        if event.key in ("up", "down"):
            event.stop()
            event.prevent_default()
            navigate = getattr(self.screen, "navigate_history", None)
            if navigate is not None:
                navigate(event.key)
        else:
            await super()._on_key(event)


class ChatScreen(VaultScreen):
    SCREEN_TITLE = "Chat"
    BOTTOM_HINTS = (
        "  [#CC785C]esc[/#CC785C] Back"
        "  [#CC785C]ctrl+y[/#CC785C] Copy answer"
        "  [#CC785C]↑↓[/#CC785C] History"
    )

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "go_back", "Back"),
        Binding("ctrl+y", "copy_answer", "Copy answer"),
    ]

    DEFAULT_CSS = """
    ChatScreen #chat-log { height: 1fr; border: none; padding: 0 2; }
    ChatScreen #thinking-line { height: 1; padding: 0 3; display: none; }
    ChatScreen #thinking-line.visible { display: block; }
    ChatScreen #input-row { height: 3; margin: 0 2 1 2; }
    ChatScreen #prompt { width: 3; height: 3; content-align: left middle; color: #CC785C; }
    ChatScreen #chat-input { width: 1fr; }
    ChatScreen #history-hint { height: 1; color: $text-muted; padding: 0 3; display: none; }
    ChatScreen #history-hint.active { display: block; }
    ChatScreen #no-model-banner {
        color: $error;
        text-align: center;
        border: round $error;
        margin: 1 2;
        padding: 1;
        display: none;
    }
    ChatScreen #no-model-banner.visible { display: block; }
    """

    def compose_content(self) -> Iterable[Widget]:
        yield Static("", id="no-model-banner", markup=True)
        yield RichLog(id="chat-log", highlight=True, markup=True, wrap=True)
        yield Static("", id="thinking-line", markup=True)
        yield Static("", id="history-hint", markup=True)
        with Horizontal(id="input-row"):
            yield Static("> ", id="prompt", markup=False)
            yield HistoryInput(
                placeholder="Ask a question about your saved posts…",
                id="chat-input",
            )

    async def on_mount(self) -> None:
        self._last_answer: str = ""
        self._input_history: list[str] = []
        self._history_index: int = -1
        self._history_stash: str = ""
        self._spin_index: int = 0
        self._spinner_timer: Timer | None = None

        from linkedin_vault.chat.session import SessionStore
        from linkedin_vault.config import load_settings
        from linkedin_vault.db.database import DatabaseManager

        self._settings = load_settings()
        self._db = DatabaseManager(self._settings.get_db_path())
        self._store = SessionStore()
        self._session = self._store.get_or_create(None)

        log = self.query_one("#chat-log", RichLog)
        chat_input = self.query_one("#chat-input", HistoryInput)

        if not self._settings.get_chat_model():
            banner = self.query_one("#no-model-banner", Static)
            banner.update(
                "[bold]No LLM model configured.[/bold] "
                "Go to Settings and configure a provider/model to use chat."
            )
            banner.add_class("visible")
            chat_input.disabled = True
            return

        await self._db.initialize_db()

        try:
            history = await self._db.get_chat_history()
            if history:
                n = len(history)
                log.write(
                    f"[dim]── {n} prior turn{'s' if n != 1 else ''} "
                    "──────────────── loaded from history ──[/dim]"
                )
                for turn in history:
                    role_label = "You" if turn["role"] == "user" else "Assistant"
                    safe = turn["content"].replace("[", r"\[")
                    log.write(f"[dim]{role_label}: {safe}[/dim]")
                log.write("[dim]──────────────────── Current Session ────────────────[/dim]")
        except Exception as exc:
            log.write(f"[dim]Could not load chat history: {exc}[/dim]")

        log.write("[dim]Vault chat ready. Ask anything about your saved posts.[/dim]")
        chat_input.focus()

    def _start_spinner(self) -> None:
        self._spin_index = 0
        self.query_one("#thinking-line", Static).add_class("visible")
        self._spinner_timer = self.set_interval(0.1, self._spin)

    def _stop_spinner(self) -> None:
        if self._spinner_timer is not None:
            self._spinner_timer.stop()
            self._spinner_timer = None
        thinking = self.query_one("#thinking-line", Static)
        thinking.remove_class("visible")
        thinking.update("")

    def _spin(self) -> None:
        frame = _SPINNER_FRAMES[self._spin_index % len(_SPINNER_FRAMES)]
        self.query_one("#thinking-line", Static).update(
            f"  [#CC785C]{frame}[/#CC785C] [dim]Thinking…[/dim]"
        )
        self._spin_index += 1

    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        if not question:
            return

        if not self._input_history or self._input_history[-1] != question:
            self._input_history.append(question)
            if len(self._input_history) > 50:
                self._input_history.pop(0)
        self._history_index = -1
        self._history_stash = ""

        hint = self.query_one("#history-hint", Static)
        hint.remove_class("active")
        hint.update("")

        event.input.clear()
        self._send_message(question)

    @work
    async def _send_message(self, question: str) -> None:
        from linkedin_vault.chat.retriever import retrieve_posts
        from linkedin_vault.chat.synthesiser import extract_citation_ids, synthesise
        from linkedin_vault.enricher.base import LLMProviderError, TransientLLMError

        log = self.query_one("#chat-log", RichLog)
        chat_input = self.query_one("#chat-input", HistoryInput)

        self._start_spinner()
        chat_input.disabled = True

        log.write(f"[#CC785C]>[/#CC785C] {question.replace('[', chr(92) + '[')}")

        try:
            top_k = max(1, min(20, self._settings.chat_top_k))
            posts = await retrieve_posts(self._db, question, top_k)

            if not posts:
                log.write(
                    "[yellow]Your vault appears to be empty. Run Scrape Posts first.[/yellow]"
                )
                return

            answer = await synthesise(question, posts, self._session.messages, self._settings)

            self._store.add_turn(self._session, question, answer)

            try:
                await self._db.save_chat_turn("user", question)
                await self._db.save_chat_turn("assistant", answer)
            except Exception as db_exc:
                log.write(f"[dim]Warning: could not save turn to history: {db_exc}[/dim]")

            self._last_answer = answer

            log.write(f"[#CC785C]●[/#CC785C] {answer.replace('[', chr(92) + '[')}")

            cited_ids = extract_citation_ids(answer)
            cited_posts = {p.id: p for p in posts if p.id in cited_ids}
            if cited_posts:
                log.write("")
                log.write("[dim]─── Sources ─────────────────────────────────[/dim]")
                for pid, p in sorted(cited_posts.items()):
                    log.write(
                        f"[dim][Post {pid}] {p.author_name} · "
                        f"{p.post_date or 'unknown'} · {p.url}[/dim]"
                    )
                log.write("")

        except (LLMProviderError, TransientLLMError) as exc:
            log.write(f"[bold red]LLM error:[/bold red] {exc}")
            exc_str = str(exc).lower()
            if "api_key" in exc_str or "401" in str(exc):
                log.write("[dim]Check your API key in Settings.[/dim]")
            elif "ollama" in exc_str:
                log.write(
                    f"[dim]Make sure Ollama is running at {self._settings.ollama_base_url}[/dim]"
                )
        except Exception as exc:
            log.write(f"[bold red]Error:[/bold red] {exc}")
        finally:
            self._stop_spinner()
            chat_input.disabled = False
            chat_input.focus()

    def action_copy_answer(self) -> None:
        if not self._last_answer:
            self.notify("Nothing to copy yet.", severity="warning", timeout=3)
            return
        self.app.copy_to_clipboard(self._last_answer)
        self.notify("Answer copied to clipboard.", timeout=3)

    def navigate_history(self, direction: str) -> None:
        if not self._input_history:
            return

        chat_input = self.query_one("#chat-input", HistoryInput)
        hint = self.query_one("#history-hint", Static)

        if direction == "up":
            if self._history_index == -1:
                self._history_stash = chat_input.value
                self._history_index = len(self._input_history) - 1
            elif self._history_index > 0:
                self._history_index -= 1
        elif direction == "down":
            if self._history_index == -1:
                return
            if self._history_index < len(self._input_history) - 1:
                self._history_index += 1
            else:
                chat_input.value = self._history_stash
                chat_input.cursor_position = len(self._history_stash)
                self._history_index = -1
                hint.remove_class("active")
                hint.update("")
                return

        if self._history_index >= 0:
            text = self._input_history[self._history_index]
            chat_input.value = text
            chat_input.cursor_position = len(text)
            pos = len(self._input_history) - self._history_index
            total = len(self._input_history)
            hint.update(f"[dim]↑ history [{pos}/{total}][/dim]")
            hint.add_class("active")

    def action_go_back(self) -> None:
        self.app.pop_screen()
