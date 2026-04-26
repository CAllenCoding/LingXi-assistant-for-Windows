import tkinter as tk
from tkinter import ttk


hs = open('聊天记录.txt', 'r', encoding='utf-8')
history_text = hs.readlines()
hs.close()
root = tk.Tk()
root.title('历史记录')
txt = tk.Text(root)
for i in history_text:
    txt.insert('end', i)
txt.pack()
def cl():
    txt.delete('1.0', 'end')
    hs = open('聊天记录.txt', 'w', encoding='utf-8')
    hs.write('')
    hs.close()
clear = ttk.Button(root, text='清空', command=cl)
clear.pack(side='right')
root.mainloop()