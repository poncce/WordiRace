class WordleBaseError(Exception):
    """Base for all domain exceptions."""


class RoomNotFoundError(WordleBaseError):
    def __init__(self, room_code: str):
        super().__init__(f"Room '{room_code}' not found")
        self.room_code = room_code


class RoomFullError(WordleBaseError):
    def __init__(self, room_code: str):
        super().__init__(f"Room '{room_code}' is full")


class RoomAlreadyStartedError(WordleBaseError):
    def __init__(self, room_code: str):
        super().__init__(f"Room '{room_code}' already has a game in progress")


class PlayerNotFoundError(WordleBaseError):
    def __init__(self, player_id: str):
        super().__init__(f"Player '{player_id}' not found")


class PlayerNotHostError(WordleBaseError):
    def __init__(self):
        super().__init__("Only the host can perform this action")


class InvalidWordLengthError(WordleBaseError):
    def __init__(self, word: str, expected: int):
        super().__init__(f"Word '{word}' has {len(word)} letters, expected {expected}")


class InvalidWordError(WordleBaseError):
    def __init__(self, word: str):
        super().__init__(f"'{word}' is not a valid Spanish word")


class GameNotActiveError(WordleBaseError):
    def __init__(self):
        super().__init__("No active game in this room")


class PlayerAlreadyFinishedError(WordleBaseError):
    def __init__(self):
        super().__init__("Player has already finished the game")


class RateLimitError(WordleBaseError):
    def __init__(self):
        super().__init__("Too many guesses, slow down")
