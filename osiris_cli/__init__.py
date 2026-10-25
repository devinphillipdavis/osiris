"""
OSIRIS Conversational Terminal REPL & Developer Experience
Version: 2.0.0
"""

__version__ = "2.0.0"


def main(argv=None) -> int:
    """Entry point for osiris_cli."""
    import sys
    from osiris_cli.session_manager import SessionManager
    from osiris_cli.conversation_router import ConversationRouter

    sm = SessionManager()
    sm.new_session()
    router = ConversationRouter(".", sm)
    if argv and len(argv) > 1:
        resp = router.route_turn(" ".join(argv[1:]))
        print(resp)
        return 0
    return 0
