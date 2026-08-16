import customtkinter as ctk

from app.theme import BORDER, FONT, TEXT, TEXT_MUTED


class StepBar(ctk.CTkFrame):
    def __init__(self, master, labels: list[str], current: int) -> None:
        super().__init__(master, fg_color="transparent")
        for index, label in enumerate(labels, start=1):
            active = index == current
            done = index < current
            color = TEXT if active or done else TEXT_MUTED

            cell = ctk.CTkFrame(self, fg_color="transparent")
            cell.pack(side="left")

            ctk.CTkLabel(
                cell,
                text=f"{index}  {label}",
                font=ctk.CTkFont(family=FONT, size=13, weight="bold" if active else "normal"),
                text_color=color,
            ).pack(side="left")

            if index < len(labels):
                ctk.CTkLabel(
                    self,
                    text="  /  ",
                    font=ctk.CTkFont(family=FONT, size=13),
                    text_color=BORDER,
                ).pack(side="left")
