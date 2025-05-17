from tkinter import Tk, Frame, Label, Button, Entry, Toplevel, messagebox
from tkinter import ttk
import tkinter as tk
import json
import os
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from itertools import accumulate

# ===== Constants =====
DATA_FILE = 'data.json'
# REVIEW_INTERVALS = [1, 3, 7, 15]
SCOPES = ['https://www.googleapis.com/auth/calendar']
GOOGLE_CALENDAR_TIMEZONE = 'Asia/Taipei'

# ===== Google Calendar Integration =====
def get_calendar_service():
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    return build('calendar', 'v3', credentials=creds)

def create_event(service, chapter, subject_name, review_intervals, start_date):
    start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    for i, interval in enumerate(list(accumulate(review_intervals)), 1):
        summary = f" {i}/{len(review_intervals)} 複習：{subject_name} - {chapter['title']}"
        day = str(start_date + timedelta(days=interval))
        event = {
            'summary': summary,
            'start': {'date': day, 'timeZone': GOOGLE_CALENDAR_TIMEZONE},
            'end': {'date': day, 'timeZone': GOOGLE_CALENDAR_TIMEZONE}
        }
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        chapter[ "event_ids" ].append(created_event['id'])

def delete_event(service, event_id):
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
    except Exception:
        pass

# ===== Data Management =====
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"review intervals": [1, 3, 7, 15], "subjects": []}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def today_str():
    return datetime.today().strftime('%Y-%m-%d')

def get_today_reviews(data):
    today = today_str()
    reviews = []
    for subject in data["subjects"]:
        for chapter in subject["chapters"]:
            if chapter.get("next_review_date") == today:
                reviews.append((subject["name"], chapter))
    return reviews

# ===== Main Application =====
class ReviewApp:
    def __init__(self, root):
        self.root = root
        self.root.title("間隔重複複習小幫手")

        self.root.geometry("500x400")
        self.root.resizable(False, False)

        self.data = load_data()
        self.service = get_calendar_service()
        self.review_intervals = self.data.get( "review intervals") # , [1, 3, 7, 15] )

        self.review_interval_var = tk.StringVar()
        self.review_interval_var.set(" ".join(map(str, self.review_intervals)))

        self.main_frame = Frame(root)
        self.main_frame.pack()

        Label(self.main_frame, text="📅 今天要複習的章節：", font=("Helvetica", 14, "bold")).pack()

        self.review_list_frame = Frame(self.main_frame)
        self.review_list_frame.pack(pady=10)

        self.refresh_review_list()

        self.subject_name_entry = Entry(self.main_frame)
        self.subject_name_entry.pack()
        self.chapter_title_entry = Entry(self.main_frame)
        self.chapter_title_entry.pack()
        self.start_date_entry = Entry(self.main_frame)
        self.start_date_entry.insert(0, today_str())
        self.start_date_entry.pack()
        Entry(self.main_frame, textvariable = self.review_interval_var).pack()
        self.message_label = Label( self.main_frame, text = "", fg = "green" )
        self.message_label.pack()

        Button( self.main_frame, text="新增科目與章節", command=self.add_subject_and_chapter).pack(pady = 5)
        Button( self.main_frame, text="📖 檢視所有科目", command=self.view_all_subjects).pack()
        Button( self.main_frame, text = "刪除所有科目", command = self.reset_all_data).pack()
        Button( self.main_frame, text = "初始化間隔時間", command = self.reset_review_interval ).pack()
        Button( self.main_frame, text = "更新間隔設定", command = self.save_interval ).pack()

    def refresh_review_list(self):
        for widget in self.review_list_frame.winfo_children():
            widget.destroy()

        reviews = get_today_reviews(self.data)
        if not reviews:
            Label(self.review_list_frame, text="🎉 沒有要複習的內容！").pack()
            return
        
        for subject_name, chapter in reviews:
            self.review_subj = tk.StringVar()
            self.review_subj.set( f"{subject_name} - {chapter['title']}" )
            Button(self.review_list_frame, textvariable = self.review_subj, command=lambda s = subject_name, c=chapter: self.mark_reviewed(c, s)).pack( pady = 2, fill = 'x' )

    def mark_reviewed(self, chapter, subject):
        if not messagebox.askyesno( "確認", f"確定 {chapter['title']} 複習完成了嗎?"):
            self.reset_review_cycle(subject, chapter)
            return

        if not chapter["next_review_date"]:
            for i, subj in enumerate( self.data["subjects"] ):
                if subj["title"] == chapter["title"]:
                    del self.data[i]
                    return
        
        chapter["start_date"] = chapter["next_review_date"]
        if len(chapter["review_dates"]) > 0:
            chapter["next_review_date"] = chapter["review_dates"][0]
            chapter["review_dates"].pop(0)
        if len(chapter["event_ids"]) > 0:
            delete_event( self.service, chapter["event_ids"][0])
            chapter["event_ids"].pop(0)
        save_data(self.data)
        self.refresh_review_list()
        
    def add_subject_and_chapter(self):
        subject_name = self.subject_name_entry.get().strip()
        chapter_title = self.chapter_title_entry.get().strip()
        start_date = self.start_date_entry.get().strip()

        if not (subject_name and chapter_title and start_date):
            messagebox.showerror("錯誤", "請填寫所有欄位")
            return

        subject = next((s for s in self.data["subjects"] if s["name"] == subject_name), None)
        if not subject:
            subject = {"name": subject_name, "chapters": []}
            self.data["subjects"].append(subject)

        existing_title =  []
        for title in subject["chapters"]:
            existing_title.append( title["title"] )

        if existing_title:
            for title in existing_title:
                if chapter_title == title:
                    messagebox.showinfo("重複標題", "章節已存在")
                    return
        
        first_review = datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=self.review_intervals[0])
        chapter = {
            "title": chapter_title,
            "start_date": start_date,
            "next_review_date": first_review.strftime('%Y-%m-%d'),
            "review_dates": [ (datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days = vals)).strftime('%Y-%m-%d')  for vals in list(accumulate(self.review_intervals))[1:]],
            "event_ids": [],
        }

        create_event(self.service, chapter, subject_name, self.review_intervals, start_date)
        subject["chapters"].append(chapter)
        save_data(self.data)
        self.refresh_review_list()

        self.message_label.config(text="新增成功!", fg="green")

        self.subject_name_entry.delete(0, tk.END)
        self.chapter_title_entry.delete(0, tk.END)
        self.start_date_entry.delete(0, tk.END)
        
        self.start_date_entry.insert(0, today_str())
        
    def view_all_subjects(self):
        win = Toplevel(self.root)
        win.title("所有科目與章節")

        if self.data['subjects'] == []:
            Label(win, text="目前沒有任何科目").pack()
        else:
            for subject in self.data["subjects"]:
                # 外框：每個科目
                subject_frame = Frame(win, bd=1, padx=10, pady=5)
                subject_frame.pack(fill="x", padx=10, pady=5, anchor="w")
                
                # 科目名稱 + 刪除科目按鈕（同一行）
                subject_top = Frame(subject_frame)
                subject_top.pack(fill="x")
                Label(subject_top, text=subject["name"], font=("Helvetica", 12, "bold")).pack(side = "left")
                Button( subject_top, text = "刪除", command = lambda s = subject: self.delete_subject(s, win) ).pack( side = "right" )
                for chapter in subject["chapters"]:
                    chapter_row = Frame(subject_frame)
                    chapter_row.pack(fill="x", padx=20, pady=2)
                    Label(chapter_row, text=f" - {chapter['title']} ({chapter.get('next_review_date', '完成')})").pack(anchor='w', side="left")
                    Button(chapter_row, text="刪除", command=lambda s=subject, c=chapter: self.delete_chapter(s, c, win)).pack( side="right")
                    # Button(chapter_row, text="複習不佳", command=lambda s=subject, c=chapter: self.reset_review_cycle(s, c)).pack(side="right")

    def delete_chapter(self, subject, chapter, window):
        if not messagebox.askyesno("確認", f"你確定要刪除「{chapter['title']}」嗎？"):
            return

        for event_id in chapter.get("event_ids"): 
            delete_event(self.service, event_id)
        subject["chapters"].remove(chapter)
        save_data(self.data)
        window.destroy()
        self.message_label.config( text = "章節刪除成功", fg = "green" )
        self.refresh_review_list()
        self.view_all_subjects()

    def delete_subject(self, subject, window):
        if messagebox.askyesno("確認刪除", f"你確定要刪除「{subject['name']}」以及其所有章節嗎？"):
            for chapter in subject.get("chapters"):
                for event_id in chapter.get("event_ids"):
                    delete_event(self.service, event_id)
        
            subject_name = subject['name']
            for i, subject in enumerate(self.data["subjects"]):
                if subject["name"] == subject_name:
                    del self.data["subjects"][i]
                    break  # 刪除後離開迴圈

            save_data(self.data)
            window.destroy()
            self.refresh_review_list()
            self.view_all_subjects()
            messagebox.showinfo("刪除成功", f"{subject_name} 已刪除")

    def reset_all_data(self):
        if messagebox.askyesno("重設所有資料", "你確定要清空所有科目與章節嗎？這個動作無法復原！"):
            # 先刪除所有章節的 Google Calendar 事件
            for subject in self.data["subjects"]:
                for chapter in subject.get("chapters", []):
                    for event_id in chapter.get("event_ids", []):
                        delete_event(self.service, event_id)

            # 清空本地資料
            self.data = {"subjects": [], "review intervals": [1, 3, 7, 15]}
            save_data(self.data)
            self.message_label.config( text = "所有資料已清空", fg = "green" )
        
    def save_interval(self):
        try:
            raw = self.review_interval_var.get()
            self.review_intervals = [int(x.strip()) for x in raw.split() if x.strip().isdigit()]
            self.data["review intervals"] = self.review_intervals
            
            self.message_label.config( text = "間隔設定更新成功!!!", fg = "green")
            save_data(self.data)
        except Exception as e:
            messagebox.showinfo( "提示", "儲存失敗" )

    def reset_review_interval(self):
        self.review_intervals = [1, 3, 7, 15]
        self.data[ "review intervals" ] = self.review_intervals
        
        save_data(self.data)
        self.message_label.config( text = "間隔初始化成功!!!", fg = "green")
        self.review_interval_var.set(" ".join(map(str, self.review_intervals)))

    def reset_review_cycle(self, subject, chapter):
        if not messagebox.askyesno("確認", f"你確定要重設「{chapter['title']}」的複習週期嗎？"):
            return
            
        # 刪除舊的 Google Calendar event
        for event_id in chapter.get("event_ids", []):
            delete_event(self.service, event_id)
        
        today = datetime.strptime(today_str(), "%Y-%m-%d")
        
        first_review = today + timedelta(days=self.review_intervals[0])
        chapter = {
            "title": chapter["title"],
            "start_date": today,
            "next_review_date": first_review.strftime('%Y-%m-%d'),
            "review_dates": [ (today + timedelta(days = vals)).strftime('%Y-%m-%d')  for vals in self.review_intervals[1:]],
            "event_ids": [],
        }

        if not isinstance(subject, str):
            subject = subject["name"]

        create_event(self.service, chapter, subject, self.review_intervals, today_str())
        self.message_label.config( text = "成功重新安排!", fg = "green" )


# ===== Run App =====
if __name__ == '__main__':
    root = Tk()
    app = ReviewApp(root)
    root.mainloop()