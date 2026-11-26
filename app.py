import streamlit as st
import httpx
from supabase import create_client, Client
import pandas as pd
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo

# הגדרת עיצוב עמוד ואייקון בדפדפן
st.set_page_config(page_title="#TOYS - ניהול חנות", page_icon="🧸", layout="wide")

IL = ZoneInfo("Asia/Jerusalem")

def today_il() -> date:
    """התאריך של היום לפי שעון ישראל (השרת של Streamlit רץ בשעון UTC)."""
    return datetime.now(IL).date()

# חיבור ל-Supabase מתוך ה-Secrets של Streamlit.
# לכל משתמש (כל לשונית דפדפן) חיבור משלו, שמור ב-session_state.
# אם החיבור היה משותף (cache_resource), כל המשתמשים היו עובדים מול ה-DB
# בזהות של מי שהתחבר אחרון.
def get_connection() -> Client:
    if "sb" not in st.session_state:
        st.session_state.sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    return st.session_state.sb

supabase: Client = get_connection()

class _Failed:
    """סימון לקריאה שנכשלה. נחשב "ריק" (False), כך ש-call(...) or [] עובד."""
    def __bool__(self):
        return False

FAILED = _Failed()

def call(fn, params=None, error="שגיאה"):
    """קריאה לפונקציה ב-Supabase.
    מחזירה את הנתונים, או FAILED אם הייתה שגיאה (ואז מציגה הודעה).
    פונקציות שלא מחזירות ערך (void) מחזירות None בהצלחה - לכן בודקים
    הצלחה עם  is not FAILED  ולא עם  is not None."""
    try:
        return supabase.rpc(fn, params or {}).execute().data
    except Exception as e:
        st.error(f"{error}: {e}")
        return FAILED

# ============================================================
# התראות לטלפון (ntfy)
# ============================================================
NTFY_SERVER = "https://ntfy.sh"

def push(topic, title, message, tags=None):
    """שליחת התראה לטלפון דרך ntfy. כישלון בשליחה לא עוצר את הפעולה עצמה."""
    if not topic:
        return False
    payload = {"topic": topic, "title": title, "message": message, "tags": tags or []}
    app_url = st.secrets.get("APP_URL")
    if app_url:
        payload["click"] = app_url  # לחיצה על ההתראה פותחת את האפליקציה
    try:
        httpx.post(NTFY_SERVER, json=payload, timeout=5).raise_for_status()
        return True
    except Exception as e:
        st.toast(f"ההתראה לטלפון לא נשלחה: {e}", icon=":material/warning:")
        return False

def push_to_user(user_id, title, message, tags=None):
    topic = call("get_ntfy_topic", {"p_user_id": user_id}, error="שגיאה באיתור ערוץ ההתראות")
    return push(topic, title, message, tags)

def push_to_admins(title, message, tags=None):
    for topic in call("get_admin_ntfy_topics", error="שגיאה באיתור ערוצי המנהלות") or []:
        push(topic, title, message, tags)

# כתובת המייל הפנימית של כל עובד ב-Supabase Auth.
# Supabase דוחה דומיינים לא אמיתיים (כמו store.local), לכן משתמשים בכתובת אמיתית
# עם תוספת "+" (Gmail מתעלם ממה שאחרי ה-+). הכתובת שמורה ב-Secrets ולא בקוד.
def auth_email(user_id):
    base = st.secrets["AUTH_EMAIL_BASE"]  # לדוגמה: "yourname@gmail.com"
    local, domain = base.split("@")
    return f"{local}+{user_id}@{domain}"

# כיווניות מימין לשמאל לכל האפליקציה
st.markdown("""
<style>
.stApp, [data-testid="stSidebar"] { direction: rtl; text-align: right; }
.stApp h1, .stApp h2, .stApp h3, .stApp p, .stApp label { text-align: right !important; }
input, textarea { direction: rtl; text-align: right; }
</style>
""", unsafe_allow_html=True)

# הפונקציה check_phone_status מחזירה רק שם ומזהה, בלי תפקיד.
# אחרי התחברות מוצלחת שולפים את פרטי המשתמש המחובר (כולל role וחובת החלפת סיסמה)
# דרך הפונקציה get_my_profile ב-Supabase.
def load_user_profile(temp_user):
    res = supabase.rpc("get_my_profile").execute()
    row = res.data or {}
    return {
        "user_id": temp_user["user_id"],
        "full_name": row.get("full_name", temp_user.get("full_name", "")),
        "role": row.get("role", "employee"),
        "must_change_password": bool(row.get("must_change_password", False)),
    }

def show_logo(width=250):
    try:
        left, center, right = st.columns([1, 1, 1])
        with center:
            st.image("logo.png", width=width)
    except Exception:
        pass

def change_password_screen():
    show_logo()
    st.title("החלפת סיסמה")
    st.info(f"שלום {st.session_state.user['full_name']}! המנהל איפס את הסיסמה שלך. נא לבחור סיסמה חדשה כדי להמשיך.")
    with st.form("change_password"):
        new_pwd = st.text_input("סיסמה חדשה:", type="password")
        confirm_pwd = st.text_input("אימות סיסמה:", type="password")
        if st.form_submit_button("שמור סיסמה"):
            if len(new_pwd) < 6:
                st.warning("הסיסמה חייבת להכיל לפחות 6 תווים.")
            elif new_pwd != confirm_pwd:
                st.warning("הסיסמאות אינן תואמות.")
            else:
                try:
                    supabase.auth.update_user({"password": new_pwd})
                    supabase.rpc("clear_must_change_password").execute()
                    st.session_state.user["must_change_password"] = False
                    st.success("הסיסמה עודכנה בהצלחה!")
                    st.rerun()
                except Exception as e:
                    st.error(f"שגיאה בעדכון הסיסמה: {e}")


# ============================================================
# משמרות וזמינות
# ============================================================
# סוגי המשמרות. כרגע רק בוקר; להוספת משמרת ערב מוסיפים כאן שורה.
SHIFT_TYPES = {
    "morning": {"label": "בוקר", "start": "10:00", "end": "16:00"},
    "noon":    {"label": "צהריים", "start": "14:00", "end": "20:00"},  # שעות זמניות, לשנות כאן
}
HE_DAYS = ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"]

def week_start_for(day: date) -> date:
    """יום ראשון של השבוע שבו נמצא התאריך."""
    return day - timedelta(days=(day.weekday() + 1) % 7)

def day_label(d: date) -> str:
    return f"{HE_DAYS[(d.weekday() + 1) % 7]} {d:%d/%m}"

def shift_type_label(k: str) -> str:
    t = SHIFT_TYPES.get(k)
    return f"{t['label']} ({t['start']}–{t['end']})" if t else k

def assign_shift(user_id, d: date, shift_type: str):
    t = SHIFT_TYPES[shift_type]
    result = call("admin_assign_shift", {
        "target_user_id": user_id,
        "p_date": d.isoformat(),
        "p_type": shift_type,
        "p_start": t["start"],
        "p_end": t["end"],
    }, error="שגיאה בשיבוץ")
    # אין התראה כאן: השיבוץ נשמר כטיוטה, וההתראה נשלחת ב"שליחת שיבוצים לעובדים"
    return result

def week_navigation():
    if "week_offset" not in st.session_state:
        st.session_state.week_offset = 0
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("שבוע קודם", icon=":material/chevron_right:"):
            st.session_state.week_offset -= 1
            st.rerun()
        if st.button("השבוע"):
            st.session_state.week_offset = 0
            st.rerun()
        if st.button("שבוע הבא", icon=":material/chevron_left:"):
            st.session_state.week_offset += 1
            st.rerun()
    start = week_start_for(today_il()) + timedelta(weeks=st.session_state.week_offset)
    return start, [start + timedelta(days=i) for i in range(7)]

def shifts_screen(user):
    is_admin = user["role"] == "admin"
    st.title("סידור עבודה")

    start, days = week_navigation()
    st.subheader(f"{days[0]:%d/%m} – {days[6]:%d/%m/%Y}")

    rows = call("get_week_shifts", {"week_start": start.isoformat()},
                error="שגיאה בטעינת המשמרות") or []

    if is_admin:
        admin_schedule_board(start, days, rows)
        return
    else:
        # ---- עובד: הגשת זמינות ----
        future_days = [d for d in days if d >= today_il()]
        with st.expander("הגשת זמינות לשבוע הזה", icon=":material/event_available:",
                         expanded=bool(future_days)):
            if not future_days:
                st.caption("השבוע הזה כבר עבר. עברו לשבוע הבא כדי להגיש זמינות.")
            else:
                st.caption("לכל יום בוחרים באילו משמרות את/ה יכול/ה לעבוד. יום בלי בחירה = לא זמין/ה.")
                with st.form(f"availability_{start.isoformat()}"):
                    # מצב נוכחי מה-DB: מה כבר הוגש ומה כבר שובץ, לכל יום
                    selections = {}
                    submitted = {}
                    for d in future_days:
                        mine = [r for r in rows if r["shift_date"] == d.isoformat()]
                        assigned = [r["shift_type"] for r in mine if r["status"] == "active"]
                        submitted[d] = {r["shift_type"]: r["shift_id"] for r in mine
                                        if r["status"] == "available"}
                        options = [k for k in SHIFT_TYPES if k not in assigned]
                        selections[d] = st.pills(
                            day_label(d), options, selection_mode="multi",
                            format_func=shift_type_label,
                            default=[k for k in submitted[d] if k in options],
                            key=f"av_{d.isoformat()}",
                        ) if options else []
                        if assigned:
                            names = ", ".join(SHIFT_TYPES.get(k, {}).get("label", k) for k in assigned)
                            st.caption(f":blue-badge[משובץ/ת: {names}]")

                    if st.form_submit_button("שליחה למנהלת", width="stretch", type="primary",
                                             icon=":material/send:"):
                        to_add = [(d, k) for d in future_days for k in selections[d]
                                  if k not in submitted[d]]
                        to_remove = [submitted[d][k] for d in future_days for k in submitted[d]
                                     if k not in selections[d]]
                        if not to_add and not to_remove:
                            st.info("לא היה שינוי בזמינות.")
                        else:
                            ok = all([
                                call("submit_availability", {
                                    "p_date": d.isoformat(), "p_type": k,
                                    "p_start": SHIFT_TYPES[k]["start"], "p_end": SHIFT_TYPES[k]["end"],
                                }, error="שגיאה בשליחת הזמינות") is not FAILED
                                for d, k in to_add
                            ] + [
                                call("withdraw_availability", {"p_shift_id": sid},
                                     error="שגיאה בביטול הזמינות") is not FAILED
                                for sid in to_remove
                            ])
                            if ok:
                                if to_add:
                                    # הודעה כללית בלי פרטים אישיים (ראו הסבר ב-ntfy.sql)
                                    push_to_admins("הגשת זמינות חדשה",
                                                   "עובד/ת הגיש/ה זמינות למשמרות. היכנסי לאפליקציה לשיבוץ.",
                                                   tags=["bell"])
                                st.toast("הזמינות עודכנה ונשלחה למנהלת.", icon=":material/check:")
                                st.rerun()

    # ---- עובד: תצוגה שבועית, כרטיס לכל יום (מתאים לטלפון) ----
    for d in days:
        day_rows = [r for r in rows if r["shift_date"] == d.isoformat()]
        with st.container(border=True):
            title = f"**{day_label(d)}**"
            if d == today_il():
                title += "  :blue-badge[היום]"
            st.markdown(title)
            if not day_rows:
                st.caption("אין משמרות")
            for r in day_rows:
                label = SHIFT_TYPES.get(r["shift_type"], {}).get("label", r["shift_type"])
                hours = f"{str(r['start_time'])[:5]}–{str(r['end_time'])[:5]}"
                with st.container(horizontal=True, vertical_alignment="center"):
                    if r["status"] == "active":
                        badge = ":blue-badge[משובץ/ת]"
                        if not r.get("is_notified"):
                            badge += " :red-badge[חדש]"
                        st.markdown(f"{badge} {label} {hours}")
                    else:  # available
                        st.markdown(f":orange-badge[הוגשה זמינות] {label} {hours}")
                        if st.button("בטל זמינות", key=f"withdraw_{r['shift_id']}",
                                     icon=":material/close:", type="tertiary"):
                            if call("withdraw_availability", {"p_shift_id": r["shift_id"]},
                                    error="שגיאה בביטול הזמינות") is not FAILED:
                                st.rerun()


# ------------------------------------------------------------
# לוח שיבוץ למנהלת
# שיבוץ = טיוטה (העובד עוד לא רואה). "שליחת שיבוצים" הופכת את כל הטיוטות
# של השבוע לשיבוץ פעיל ושולחת לכל עובד התראה אחת מסכמת.
# ------------------------------------------------------------
def shift_sort_key(r):
    return (r["shift_date"], list(SHIFT_TYPES).index(r["shift_type"]) if r["shift_type"] in SHIFT_TYPES else 99)

def shift_text(r):
    t = SHIFT_TYPES.get(r["shift_type"], {})
    return f"{day_label(date.fromisoformat(r['shift_date']))} {t.get('label', r['shift_type'])} {t.get('start', '')}–{t.get('end', '')}"

def admin_schedule_board(start, days, rows):
    planned = [r for r in rows if r["status"] == "planned"]
    pending = [r for r in rows if r["status"] == "available"]

    # ---- שליחה לעובדים ----
    with st.container(horizontal=True, vertical_alignment="center"):
        st.metric("טיוטות שלא נשלחו", len(planned), border=True)
        st.metric("זמינויות ממתינות", len(pending), border=True)
    if st.button(f"שליחת שיבוצים לעובדים ({len(planned)})", type="primary",
                 icon=":material/send:", disabled=not planned, width="stretch"):
        sent = call("admin_publish_week", {"p_week_start": start.isoformat()},
                    error="שגיאה בשליחת השיבוצים")
        if sent is not FAILED:
            by_user = {}
            for s in sent or []:
                by_user.setdefault(s["user_id"], []).append(s)
            for uid, items in by_user.items():
                lines = [shift_text(i) for i in sorted(items, key=shift_sort_key)]
                push_to_user(uid, f"סידור העבודה שלך ({len(items)} משמרות)", "\n".join(lines),
                             tags=["calendar"])
            st.toast(f"השיבוצים נשלחו ל-{len(by_user)} עובדים.", icon=":material/check:")
            st.rerun()
    if planned:
        st.caption("📝 טיוטה = שובץ אבל עוד לא נשלח. העובדים יראו את השיבוץ ויקבלו התראה רק אחרי השליחה.")

    st.caption("הסידור הסופי (מה שכבר נשלח לעובדים) מופיע בלשונית **סידור שבועי**.")

    # ---- לוח שיבוץ: יום = שורה, משמרת = עמודה ----
    employees = call("admin_list_users", error="שגיאה בטעינת העובדים") or []
    for d in days:
        day_rows = [r for r in rows if r["shift_date"] == d.isoformat()]
        with st.container(border=True):
            title = f"**{day_label(d)}**"
            if d == today_il():
                title += "  :blue-badge[היום]"
            st.markdown(title)
            for col, (k, t) in zip(st.columns(len(SHIFT_TYPES)), SHIFT_TYPES.items()):
                with col:
                    shift_cell(d, k, t, day_rows, employees)


# ------------------------------------------------------------
# סידור שבועי סופי - למנהלת
# מציג רק שיבוצים שנשלחו לעובדים (status = active).
# ------------------------------------------------------------
def weekly_schedule_screen():
    st.title("סידור עבודה שבועי")
    start, days = week_navigation()
    st.subheader(f"{days[0]:%d/%m} – {days[6]:%d/%m/%Y}")

    rows = call("get_week_shifts", {"week_start": start.isoformat()},
                error="שגיאה בטעינת המשמרות") or []
    final = [r for r in rows if r["status"] == "active"]
    drafts = [r for r in rows if r["status"] == "planned"]

    if drafts:
        st.warning(f"{len(drafts)} שיבוצים בטיוטה עוד לא נשלחו לעובדים ולכן לא מופיעים כאן. "
                   "כדי לשלוח: מסך **משמרות** ← **שליחת שיבוצים לעובדים**.", icon=":material/info:")
    if not final:
        st.caption("אין עדיין שיבוצים שנשלחו לשבוע הזה.")
        return

    with st.container(horizontal=True):
        st.metric("משמרות בשבוע", len(final), border=True)
        st.metric("עובדים משובצים", len({r["user_id"] for r in final}), border=True)

    view = st.segmented_control("תצוגה", ["לפי משמרות", "לפי עובדים"], default="לפי משמרות",
                                required=True, label_visibility="collapsed", key="sched_view")

    if view == "לפי משמרות":
        table = []
        for d in days:
            row = {"יום": day_label(d)}
            for k, t in SHIFT_TYPES.items():
                names = sorted(r["full_name"] for r in final
                               if r["shift_date"] == d.isoformat() and r["shift_type"] == k)
                row[f"{t['label']} {t['start']}–{t['end']}"] = ", ".join(names) or "—"
            table.append(row)
        df = pd.DataFrame(table).set_index("יום")
    else:
        names = sorted({r["full_name"] for r in final})
        table = []
        for name in names:
            mine = [r for r in final if r["full_name"] == name]
            row = {"עובד/ת": name}
            for d in days:
                labels = [SHIFT_TYPES.get(r["shift_type"], {}).get("label", r["shift_type"])
                          for r in sorted(mine, key=shift_sort_key) if r["shift_date"] == d.isoformat()]
                row[day_label(d)] = " + ".join(labels) or "—"
            row["סה\"כ"] = len(mine)
            table.append(row)
        df = pd.DataFrame(table).set_index("עובד/ת")

    st.table(df)
    st.download_button(
        "הורדה לאקסל (CSV)", df.to_csv().encode("utf-8-sig"),
        file_name=f"schedule_{start.isoformat()}.csv", mime="text/csv",
        icon=":material/download:",
    )

def shift_cell(d, k, t, day_rows, employees):
    st.markdown(f"**{t['label']}** · {t['start']}–{t['end']}")
    cell = [r for r in day_rows if r["shift_type"] == k]
    assigned = [r for r in cell if r["status"] in ("planned", "active")]
    available = [r for r in cell if r["status"] == "available"]

    for r in assigned:
        with st.container(horizontal=True, vertical_alignment="center"):
            badge = ":green-badge[✅ נשלח]" if r["status"] == "active" else ":orange-badge[📝 טיוטה]"
            st.markdown(f"{badge} {r['full_name']}")
            if st.button("הסר", key=f"rm_{r['shift_id']}", icon=":material/close:", type="tertiary"):
                if call("admin_cancel_shift", {"p_shift_id": r["shift_id"]},
                        error="שגיאה בהסרה") is not FAILED:
                    if r["status"] == "active":  # העובד כבר קיבל את השיבוץ - מודיעים לו
                        push_to_user(r["user_id"], "משמרת בוטלה",
                                     f"המשמרת שלך: {shift_text(r)} - בוטלה", tags=["x"])
                    st.rerun()

    for r in available:
        # האם אותו עובד זמין / משובץ גם למשמרת אחרת באותו יום?
        other = [o for o in day_rows if o["user_id"] == r["user_id"] and o["shift_type"] != k]
        notes = []
        for o in other:
            label = SHIFT_TYPES.get(o["shift_type"], {}).get("label", o["shift_type"])
            notes.append(f"משובץ/ת ל{label}" if o["status"] in ("planned", "active") else f"זמין/ה גם ל{label}")
        new = " :red-badge[חדש]" if not r.get("is_notified") else ""
        st.markdown(f":blue-badge[זמין/ה]{new} {r['full_name']}"
                    + (f"  \n:gray[{' · '.join(notes)}]" if notes else ""))
        with st.container(horizontal=True):
            if st.button("שבץ", key=f"ok_{r['shift_id']}", icon=":material/check:", type="primary"):
                if assign_shift(r["user_id"], d, k) is not FAILED:
                    st.rerun()
            if st.button("דחה", key=f"no_{r['shift_id']}", icon=":material/close:", type="tertiary"):
                if call("admin_cancel_shift", {"p_shift_id": r["shift_id"]},
                        error="שגיאה בדחייה") is not FAILED:
                    st.rerun()

    if not assigned and not available:
        st.caption("אין עובדים")

    taken = {r["user_id"] for r in assigned}
    choices = {e["full_name"]: e["id"] for e in employees if e["id"] not in taken}
    if choices:
        with st.popover("שיבוץ ידני", icon=":material/person_add:"):
            name = st.selectbox("עובד/ת", list(choices.keys()), key=f"pick_{d.isoformat()}_{k}")
            if st.button("שבץ", key=f"add_{d.isoformat()}_{k}", type="primary", width="stretch"):
                if assign_shift(choices[name], d, k) is not FAILED:
                    st.rerun()


# ============================================================
# משימות
# ============================================================
def format_due(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(IL).strftime("%d/%m %H:%M")
    except ValueError:
        return value

def tasks_screen(user):
    is_admin = user["role"] == "admin"
    st.title("משימות")

    if is_admin:
        with st.expander("משימה חדשה", icon=":material/add_task:"):
            employees = [emp for emp in (call("admin_list_users", error="שגיאה בטעינת העובדים") or [])
                         if emp.get("role") != "admin"]
            emp_ids = {emp["full_name"]: emp["id"] for emp in employees}
            with st.form("new_task", clear_on_submit=True):
                title = st.text_input("כותרת")
                description = st.text_area("פירוט (לא חובה)")
                for_all = st.toggle("משימה משותפת לכל העובדים")
                chosen = st.multiselect("או: לאילו עובדים (אפשר לבחור כמה)", list(emp_ids.keys()),
                                        placeholder="בחירת עובדים")
                due_date = st.date_input("תאריך יעד (לא חובה)", value=None, format="DD/MM/YYYY")
                due_time = st.time_input("שעה", value=time(10, 0))
                if st.form_submit_button("יצירת משימה", width="stretch", type="primary"):
                    if not title.strip():
                        st.warning("חובה להזין כותרת.")
                    elif not for_all and not chosen:
                        st.warning("נא לבחור עובד אחד או יותר, או לסמן \"משימה משותפת לכל העובדים\".")
                    else:
                        due = (datetime.combine(due_date, due_time, tzinfo=IL).isoformat()
                               if due_date else None)
                        targets = [] if for_all else [emp_ids[name] for name in chosen]
                        if call("admin_create_tasks", {
                            "p_title": title,
                            "p_description": description or None,
                            "p_assigned_to": targets,
                            "p_scheduled_for": due,
                        }, error="שגיאה ביצירת המשימה") is not FAILED:
                            recipients = targets or [emp["id"] for emp in employees]
                            msg = title.strip() + (f" (עד {format_due(due)})" if due else "")
                            for uid in recipients:
                                push_to_user(uid, "משימה חדשה", msg, tags=["memo"])
                            st.toast(f"המשימה נוצרה ל-{len(recipients)} עובדים.", icon=":material/check:")
                            st.rerun()

    view = st.segmented_control("הצגה", ["פתוחות", "בוצעו"], default="פתוחות",
                                required=True, label_visibility="collapsed")
    wanted = "done" if view == "בוצעו" else "open"
    tasks = [t for t in (call("get_tasks", error="שגיאה בטעינת המשימות") or [])
             if (t.get("status") or "open") == wanted]

    if not tasks:
        st.caption("אין משימות להצגה.")
    for t in tasks:
        with st.container(border=True):
            badges = []
            if not t.get("is_notified") and not is_admin and t.get("assigned_to"):
                badges.append(":red-badge[חדש]")
            badges.append(f":violet-badge[{t.get('assignee_name') or 'כל העובדים'}]")
            due = format_due(t.get("scheduled_for"))
            if due:
                badges.append(f":orange-badge[:material/schedule: {due}]")
            if wanted == "done" and t.get("completed_by_name"):
                badges.append(f":green-badge[:material/check: בוצע ע\"י {t['completed_by_name']}"
                              f"{' · ' + format_due(t['completed_at']) if t.get('completed_at') else ''}]")
            st.markdown(f"**{t['title']}**  \n" + " ".join(badges))
            if t.get("description"):
                st.caption(t["description"])
            with st.container(horizontal=True):
                if wanted == "open":
                    if st.button("✓ בוצע", key=f"done_{t['task_id']}", type="primary"):
                        if call("set_task_status", {"p_task_id": t["task_id"], "p_status": "done"},
                                error="שגיאה בעדכון") is not FAILED:
                            if not is_admin:
                                # הודעה למנהלת. בלי שם העובד - ראו הסבר ב-ntfy.sql
                                push_to_admins("משימה הושלמה", f"✓ {t['title']}", tags=["white_check_mark"])
                            st.toast("כל הכבוד! המשימה סומנה כבוצעה.", icon=":material/check:")
                            st.rerun()
                else:
                    if st.button("החזרה לפתוחה", key=f"reopen_{t['task_id']}",
                                 icon=":material/undo:"):
                        if call("set_task_status", {"p_task_id": t["task_id"], "p_status": "open"},
                                error="שגיאה בעדכון") is not FAILED:
                            st.rerun()
                if is_admin and st.button("מחיקה", key=f"cancel_task_{t['task_id']}",
                                          icon=":material/delete:", type="tertiary"):
                    if call("set_task_status", {"p_task_id": t["task_id"], "p_status": "cancelled"},
                            error="שגיאה במחיקה") is not FAILED:
                        st.rerun()


# ============================================================
# מכירות
# ============================================================
def month_bounds(day: date):
    first = day.replace(day=1)
    next_first = (first + timedelta(days=32)).replace(day=1)
    return first, next_first - timedelta(days=1)

def sales_leaderboard(me_name=None, key="lb"):
    """טבלת המכירות של הצוות - תחרות פנימית. כל משתמש רואה."""
    st.subheader("🏆 טבלת המכירות של הצוות")
    period = st.segmented_control("תקופה", ["השבוע", "החודש"], default="השבוע",
                                  required=True, key=f"{key}_period", label_visibility="collapsed")
    today = today_il()
    if period == "השבוע":
        p_from, p_to = week_start_for(today), week_start_for(today) + timedelta(days=6)
    else:
        p_from, p_to = month_bounds(today)
    rows = call("get_sales_leaderboard", {"p_from": p_from.isoformat(), "p_to": p_to.isoformat()},
                error="שגיאה בטעינת טבלת המכירות") or []
    if not rows:
        st.caption("עדיין אין דיווחים בתקופה הזו.")
        return
    df = pd.DataFrame(rows)
    df["total_amount"] = df["total_amount"].astype(float)
    medals = ["🥇", "🥈", "🥉"]
    df.insert(0, "place", [medals[i] if i < 3 else str(i + 1) for i in range(len(df))])
    if me_name and me_name in df["full_name"].values:
        place = int(df.index[df["full_name"] == me_name][0]) + 1
        st.markdown(f"את/ה במקום **{place}** מתוך {len(df)} 💪")
    st.dataframe(
        df,
        hide_index=True,
        column_order=["place", "full_name", "total_amount", "transactions"],
        column_config={
            "place": st.column_config.TextColumn("מקום", width="small"),
            "full_name": st.column_config.TextColumn("עובד/ת"),
            "total_amount": st.column_config.ProgressColumn(
                "סך מכירות", format="₪%.0f", min_value=0,
                max_value=float(df["total_amount"].max()) or 1.0),
            "transactions": st.column_config.NumberColumn("עסקאות"),
        },
        alt="טבלת המכירות של הצוות",
    )

def sales_report_screen(user):
    """עובד: דיווח מכירות יומי + טבלת הצוות."""
    st.title("דיווח מכירות יומי")
    today = today_il()
    now = datetime.now(IL)
    with st.form("sales_report", clear_on_submit=True):
        # יום ושעה של הדיווח (ברירת מחדל: עכשיו). עד 30 יום אחורה, לא בעתיד.
        with st.container(horizontal=True):
            sale_date = st.date_input("תאריך", value=today, min_value=today - timedelta(days=30),
                                      max_value=today, format="DD/MM/YYYY")
            sale_time = st.time_input("שעה", value=time(now.hour, now.minute), step=timedelta(minutes=5))
        # שדות ריקים (בלי 0.00 מוכן מראש) - מקלידים ישר, אפשר גם אגורות
        sales_amount = st.number_input("סך מכירות במשמרת (₪)", min_value=0.0, value=None,
                                       step=0.01, format="%.2f", placeholder="למשל 1250.50")
        trans_count = st.number_input("מספר עסקאות / לקוחות", min_value=0, value=None, step=1,
                                      placeholder="למשל 14")
        notes = st.text_area("הערות נוספות")
        if st.form_submit_button("שמירת דיווח", width="stretch", type="primary",
                                 icon=":material/save:"):
            if sales_amount is None:
                st.warning("נא להזין את סך המכירות.")
            elif call("submit_sales_report", {
                "p_amount": round(float(sales_amount), 2),
                "p_count": int(trans_count or 0),
                "p_notes": notes,
                "p_date": sale_date.isoformat(),
                "p_time": sale_time.strftime("%H:%M"),
            }, error="שגיאה בשמירת הדיווח") is not FAILED:
                st.toast("הדיווח נשמר בהצלחה!", icon=":material/check:")
                st.rerun()

    sales_leaderboard(me_name=user["full_name"], key="lb_emp")

    mine = call("get_my_sales", {"p_from": (today - timedelta(days=30)).isoformat(),
                                 "p_to": today.isoformat()},
                error="שגיאה בטעינת הדיווחים") or []
    if mine:
        st.subheader("הדיווחים האחרונים שלי")
        st.dataframe(
            pd.DataFrame(mine),
            hide_index=True,
            column_config={
                "sale_date": st.column_config.DateColumn("תאריך", format="DD/MM/YYYY"),
                "sale_time": st.column_config.TextColumn("שעה"),
                "total_amount": st.column_config.NumberColumn("סכום", format="₪%.2f"),
                "transactions_count": st.column_config.NumberColumn("עסקאות"),
                "notes": st.column_config.TextColumn("הערות"),
            },
            alt="הדיווחים האחרונים שלי",
        )

def sales_admin_screen():
    """מנהלת: טבלת הצוות + צפייה בכל הדיווחים ועריכה."""
    st.title("מכירות")
    sales_leaderboard(key="lb_admin")
    st.subheader("כל הדיווחים")
    today = today_il()
    period = st.date_input("טווח תאריכים", value=(today - timedelta(days=6), today),
                           format="DD/MM/YYYY")
    if not isinstance(period, tuple) or len(period) != 2:
        st.caption("נא לבחור תאריך התחלה ותאריך סיום.")
        return
    p_from, p_to = period

    rows = call("admin_list_sales", {"p_from": p_from.isoformat(), "p_to": p_to.isoformat()},
                error="שגיאה בטעינת המכירות") or []
    if not rows:
        st.caption("אין דיווחים בטווח הזה.")
        return

    df = pd.DataFrame(rows).set_index("sale_id")
    df["total_amount"] = df["total_amount"].astype(float)
    df["transactions_count"] = df["transactions_count"].fillna(0).astype(int)
    df["notes"] = df["notes"].fillna("")

    with st.container(horizontal=True):
        st.metric("סך מכירות", f"₪{df['total_amount'].sum():,.2f}", border=True)
        st.metric("עסקאות", f"{df['transactions_count'].sum():,}", border=True)
        st.metric("דיווחים", len(df), border=True)

    st.caption("אפשר לערוך סכום, עסקאות והערות ישירות בטבלה ואז ללחוץ **שמירת שינויים**. כל שינוי נשמר בהיסטוריה.")
    edited = st.data_editor(
        df,
        hide_index=True,
        disabled=["full_name", "sale_date", "sale_time"],
        column_order=["full_name", "sale_date", "sale_time", "total_amount", "transactions_count", "notes"],
        column_config={
            "full_name": st.column_config.TextColumn("עובד"),
            "sale_date": st.column_config.DateColumn("תאריך", format="DD/MM/YYYY"),
            "sale_time": st.column_config.TextColumn("שעה"),
            "total_amount": st.column_config.NumberColumn("סכום", format="₪%.2f", min_value=0),
            "transactions_count": st.column_config.NumberColumn("עסקאות", min_value=0, step=1),
            "notes": st.column_config.TextColumn("הערות"),
        },
        key="sales_editor",
        alt="דיווחי מכירות",
    )

    cols = ["total_amount", "transactions_count", "notes"]
    changed = [sid for sid in df.index
               if [str(v) for v in edited.loc[sid, cols]] != [str(v) for v in df.loc[sid, cols]]]
    if st.button(f"שמירת שינויים ({len(changed)})", type="primary", icon=":material/save:",
                 disabled=not changed):
        ok = all(
            call("admin_update_sale", {
                "p_sale_id": sid,
                "p_amount": float(edited.loc[sid, "total_amount"]),
                "p_count": int(edited.loc[sid, "transactions_count"]),
                "p_notes": edited.loc[sid, "notes"],
            }, error="שגיאה בעדכון הדיווח") is not FAILED
            for sid in changed
        )
        if ok:
            st.toast("השינויים נשמרו.", icon=":material/check:")
            st.rerun()


# ============================================================
# מסך "התראות": הגדרות + חיבור הטלפון
# ============================================================
def phone_notifications_screen(user):
    st.title("התראות")
    settings = call("get_my_notification_settings", error="שגיאה בטעינת ההגדרות")
    if not settings:
        st.warning("לא נמצאו הגדרות התראות. ודאי שהקבצים features.sql ו-ntfy.sql הורצו ב-Supabase.")
        return

    # כל משתמש יכול לכבות כל סוג התראה
    with st.container(border=True):
        st.markdown("**מה לקבל?**")
        push_on = st.toggle("התראות לטלפון (גם כשהאפליקציה סגורה)",
                            value=bool(settings.get("notify_push")), key="set_push")
        in_app_on = st.toggle("התראות בתוך האפליקציה",
                              value=bool(settings.get("notify_in_app")), key="set_in_app")
        if (push_on, in_app_on) != (bool(settings.get("notify_push")), bool(settings.get("notify_in_app"))):
            if call("set_my_notification_settings", {"p_push": push_on, "p_in_app": in_app_on},
                    error="שגיאה בשמירת ההגדרות") is not FAILED:
                st.toast("ההגדרות נשמרו.", icon=":material/check:")

    if not push_on:
        st.caption("התראות לטלפון כבויות. אפשר להפעיל אותן מחדש בכל רגע.")
        return

    st.subheader("חיבור הטלפון")
    st.write("כדי לקבל התראה לטלפון על משמרות ומשימות, גם כשהאפליקציה סגורה:")
    st.markdown(
        "1. מתקינים את האפליקציה החינמית **ntfy**: "
        "[אייפון](https://apps.apple.com/app/ntfy/id1625396347) · "
        "[אנדרואיד](https://play.google.com/store/apps/details?id=io.heckel.ntfy)\n"
        "2. באייפון: מאשרים התראות (**Allow**) בפתיחה הראשונה.\n"
        "3. לוחצים על **+** (Subscribe to topic) ומדביקים את שם הערוץ שלך:"
    )
    st.caption("צריכים הדרכה צעד אחר צעד? שאלו את **סוכן AI חכם**: \"איך מתקינים התראות?\"")
    topic = settings.get("topic")
    if not topic:
        st.warning("לא נמצא ערוץ התראות. ודאי שהקובץ ntfy.sql הורץ ב-Supabase.")
        return
    st.code(topic, language=None)
    st.caption("לחיצה על סמל ההעתקה בצד הקוד מעתיקה את השם. אל תשתפו אותו - מי שיודע אותו יכול לקרוא את ההתראות שלך.")

    with st.container(horizontal=True):
        if st.button("שלח התראת בדיקה", icon=":material/send:", type="primary"):
            if push(topic, "בדיקה מ-#TOYS", "ההתראות עובדות! 🎉", tags=["tada"]):
                st.toast("נשלחה התראת בדיקה. בדקו את הטלפון.", icon=":material/check:")
        if st.button("החלפת ערוץ", icon=":material/refresh:", type="tertiary",
                     help="אם שם הערוץ דלף. אחרי ההחלפה צריך להירשם מחדש באפליקציית ntfy."):
            if call("regenerate_my_ntfy_topic", error="שגיאה בהחלפת הערוץ"):
                st.rerun()


# ============================================================
# סוכן AI - שיחה
# הסוכן מזהה את נושא השאלה לפי מילות מפתח.
# שאלות עזרה (התקנת התראות / התקנת האפליקציה בטלפון) פתוחות לכולם,
# ובסוף התשובה הוא שואל "אייפון או אנדרואיד?" עם כפתורים, ואז מדריך צעד אחר צעד.
# שאלות על נתוני החנות - למנהלת בלבד.
# ============================================================
HELP_GUIDES = {
    ("notifications", "iphone"): [
        "פתחו את **App Store** וחפשו **ntfy** (אפליקציה חינמית). לחצו **השג** והתקינו.",
        "פתחו את ntfy. כשמופיעה השאלה על התראות - לחצו **Allow** (אפשר).",
        "חזרו לאפליקציית החנות ← לחצו על **התראות** בתפריט ← העתיקו את שם הערוץ שלכם (סמל ההעתקה).",
        "ב-ntfy לחצו על **+** למעלה, הדביקו את שם הערוץ בשדה **Topic** ולחצו **Subscribe**.",
        "חזרו לאפליקציית החנות ולחצו **שלח התראת בדיקה** - תוך כמה שניות אמורה לקפוץ התראה.",
        "לא הגיעה התראה? **הגדרות** ← **התראות** ← **ntfy** ← ודאו ש**אפשר התראות** דולק.",
    ],
    ("notifications", "android"): [
        "פתחו את **Google Play** וחפשו **ntfy** (אפליקציה חינמית). לחצו **התקנה**.",
        "פתחו את ntfy. אם הטלפון שואל על הרשאה להתראות - לחצו **אישור**.",
        "חזרו לאפליקציית החנות ← לחצו על **התראות** בתפריט ← העתיקו את שם הערוץ שלכם (סמל ההעתקה).",
        "ב-ntfy לחצו על **+** (למטה), הדביקו את שם הערוץ בשדה **Topic** ולחצו **Subscribe**.",
        "חזרו לאפליקציית החנות ולחצו **שלח התראת בדיקה** - תוך כמה שניות אמורה לקפוץ התראה.",
        "לא הגיעה התראה? **הגדרות** ← **אפליקציות** ← **ntfy** ← **סוללה** ← בחרו **ללא הגבלה**, כדי שהטלפון לא יסגור אותה ברקע.",
    ],
    ("install", "iphone"): [
        "פתחו את הקישור של אפליקציית החנות בדפדפן **Safari**.",
        "לחצו על כפתור **השיתוף** בתחתית המסך (ריבוע עם חץ למעלה).",
        "גללו למטה ובחרו **הוסף למסך הבית**.",
        "אפשר לשנות את השם ל-**#TOYS**, ואז לחצו **הוסף** (למעלה).",
        "זהו! האייקון של האפליקציה מופיע במסך הבית ונפתח כמו אפליקציה רגילה.",
    ],
    ("install", "android"): [
        "פתחו את הקישור של אפליקציית החנות בדפדפן **Chrome**.",
        "לחצו על **⋮** (שלוש נקודות) בפינה העליונה.",
        "בחרו **הוספה למסך הבית** (או **התקנת אפליקציה**, אם מופיע).",
        "אשרו בלחיצה על **הוספה**.",
        "זהו! האייקון של האפליקציה מופיע במסך הבית ונפתח כמו אפליקציה רגילה.",
    ],
}
HELP_TITLES = {
    "notifications": "איך מתקינים את ההתראות לטלפון",
    "install": "איך מוסיפים את אפליקציית החנות למסך הבית",
}
DEVICES = {"iphone": "אייפון", "android": "אנדרואיד"}

def has_any(text, words):
    return any(w in text for w in words)

def detect_topic(q: str):
    q = q.lower()
    if has_any(q, ["התראה", "התראות", "ntfy", "נוטיפיקציה", "הודעות לטלפון", "פוש", "push"]):
        return "notifications"
    if has_any(q, ["להוריד", "הורד", "מוריד", "להתקין", "התקנ", "מתקינ", "מסך הבית", "קישור",
                   "url", "לינק", "אייקון", "אפליקציה"]):
        return "install"
    if has_any(q, ["אני זמינה", "אני זמין", "זמינה בכל", "זמין בכל", "זמינה תמיד", "זמין תמיד"]):
        return "admin_available"
    if has_any(q, ["תמליץ", "המלצ", "הצע", "תבנה", "בנה", "תסדר", "סדר לי", "סידור"]):
        return "schedule"
    if has_any(q, ["עובדים", "צוות"]):
        return "staff"
    if has_any(q, ["משמרת", "משמרות", "שיבוץ", "שיבוצים", "משובץ", "לעבוד", "עובד/ת מתי"]):
        return "shifts"
    if has_any(q, ["מכר", "מכירות", "כסף", "הכנסות", "דוחות", "הרווחתי", "עסקאות"]):
        return "sales"
    return "other"

def parse_period(q: str, default="month"):
    """מזהה תקופה מתוך השאלה. מחזיר (מתאריך, עד תאריך, תיאור)."""
    import re
    today = today_il()
    dates = []
    for d, m, y in re.findall(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", q):
        year = int(y) + (2000 if y and len(y) == 2 else 0) if y else today.year
        try:
            dates.append(date(year, int(m), int(d)))
        except ValueError:
            pass
    if len(dates) >= 2:
        a, b = sorted(dates[:2])
        return a, b, f"{a:%d/%m}–{b:%d/%m}"
    if len(dates) == 1:
        return dates[0], dates[0], f"{dates[0]:%d/%m}"

    week = week_start_for(today)
    if "אתמול" in q:
        y = today - timedelta(days=1)
        return y, y, "אתמול"
    if "מחר" in q and "מחרתיים" not in q:
        t = today + timedelta(days=1)
        return t, t, "מחר"
    if "היום" in q:
        return today, today, "היום"
    if has_any(q, ["שבוע שעבר", "השבוע שעבר", "שבוע הקודם", "השבוע הקודם"]):
        return week - timedelta(days=7), week - timedelta(days=1), "בשבוע שעבר"
    if has_any(q, ["שבוע הבא", "השבוע הבא"]):
        return week + timedelta(days=7), week + timedelta(days=13), "בשבוע הבא"
    if "השבוע" in q or "שבוע" in q:
        return week, week + timedelta(days=6), "השבוע"
    if has_any(q, ["חודש שעבר", "החודש שעבר", "חודש הקודם", "החודש הקודם"]):
        first, _ = month_bounds(today)
        return month_bounds(first - timedelta(days=1)) + ("בחודש שעבר",)
    if has_any(q, ["חודש הבא", "החודש הבא"]):
        _, last = month_bounds(today)
        return month_bounds(last + timedelta(days=1)) + ("בחודש הבא",)
    if default == "week":
        return week, week + timedelta(days=6), "השבוע"
    return month_bounds(today) + ("החודש",)

def my_shifts_answer(q):
    p_from, p_to, label = parse_period(q)
    rows = call("get_my_shifts", {"p_from": p_from.isoformat(), "p_to": p_to.isoformat()},
                error="שגיאה בטעינת המשמרות")
    if rows is FAILED:
        return {"role": "assistant", "content": "לא הצלחתי לטעון את המשמרות כרגע."}
    if not rows:
        return {"role": "assistant", "content": f"אין לך משמרות {label}."}
    lines = [f"- {day_label(date.fromisoformat(r['shift_date']))}: "
             f"{SHIFT_TYPES.get(r['shift_type'], {}).get('label', r['shift_type'])} "
             f"{str(r['start_time'])[:5]}–{str(r['end_time'])[:5]}" for r in rows]
    return {"role": "assistant",
            "content": f"📅 יש לך **{len(rows)}** משמרות {label}:\n" + "\n".join(lines)}

def my_sales_answer(q):
    p_from, p_to, label = parse_period(q)
    rows = call("get_my_sales", {"p_from": p_from.isoformat(), "p_to": p_to.isoformat()},
                error="שגיאה בטעינת המכירות")
    if rows is FAILED:
        return {"role": "assistant", "content": "לא הצלחתי לטעון את המכירות כרגע."}
    if not rows:
        return {"role": "assistant", "content": f"אין לך דיווחי מכירות {label}."}
    total = sum(float(r["total_amount"] or 0) for r in rows)
    deals = sum(int(r["transactions_count"] or 0) for r in rows)
    lines = [f"- {day_label(date.fromisoformat(r['sale_date']))}: ₪{float(r['total_amount'] or 0):,.0f}"
             for r in rows]
    return {"role": "assistant",
            "content": f"💰 מכרת **₪{total:,.0f}** {label} ({deals} עסקאות, {len(rows)} דיווחים):\n"
                       + "\n".join(lines)}

def guide_message(topic, device):
    steps = HELP_GUIDES[(topic, device)]
    text = f"**{HELP_TITLES[topic]} - {DEVICES[device]}:**\n\n"
    text += "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    app_url = st.secrets.get("APP_URL")
    if topic == "install" and app_url:
        text += f"\n\nהקישור לאפליקציה: {app_url}"
    return {"role": "assistant", "content": text}

def agent_answer(q: str, user, dash):
    topic = detect_topic(q)
    is_admin = user["role"] == "admin"

    if topic in ("notifications", "install"):
        intro = ("אשמח לעזור להתקין את ההתראות לטלפון 🔔"
                 if topic == "notifications" else
                 "אשמח לעזור להוסיף את אפליקציית החנות למסך הבית 📱")
        return {"role": "assistant", "content": intro + "\n\n**איזה טלפון יש לך?**",
                "ask_device": topic}

    # עובד: רק שאלות על עצמו
    if not is_admin:
        if topic in ("shifts", "schedule"):
            return my_shifts_answer(q)
        if topic == "sales":
            return my_sales_answer(q)
        if topic == "admin_available":
            return {"role": "assistant",
                    "content": "כדי לעדכן מתי את/ה זמין/ה - היכנס/י למסך **משמרות** ← **הגשת זמינות**."}

    # מנהלת: "אני זמינה בכל יום" -> הסוכן ישלים איתה משמרות חסרות
    if topic == "admin_available":
        return {"role": "assistant",
                "content": "רשמתי 👍 בהמלצות לסידור אשלים איתך משמרות שאין להן מספיק עובדים. "
                           "רוצה שאמליץ עכשיו על סידור לשבוע הבא?"}

    # מנהלת: המלצה על סידור לפי הזמינות שהעובדים הגישו
    if topic in ("schedule", "shifts"):
        this_week = "השבוע" in q and not has_any(q, ["הבא", "הקרוב"])
        start = week_start_for(today_il()) + timedelta(weeks=0 if this_week else 1)
        return {"role": "assistant",
                "content": f"📅 **הצעה לסידור {start:%d/%m}–{start + timedelta(days=6):%d/%m}**, "
                           "לפי הזמינות שהעובדים שלחו. אפשר לשנות כמה עובדים צריך בכל משמרת, "
                           "ואז לאשר - ההצעה תישמר כ**טיוטה** ותוכלי לשנות אותה לפני השליחה לעובדים.",
                "proposal": start.isoformat()}

    if topic == "sales" and is_admin:
        sales = dash.get("sales") or []
        if not sales:
            return {"role": "assistant", "content": "עדיין לא הוזנו דיווחי מכירות במערכת."}
        total = sum(float(s["total_amount"] or 0) for s in sales)
        return {"role": "assistant",
                "content": f"📊 סך כל המכירות במערכת: **₪{total:,.2f}** לאורך {len(sales)} דיווחים.",
                "table": sales}

    if topic == "staff" and is_admin:
        users = dash.get("users") or []
        return {"role": "assistant",
                "content": "👥 מצבת העובדים. 💡 המלצה: לוודא לפחות 2 עובדים בכל משמרת בסופי שבוע, ולשבץ לפחות 48 שעות מראש.",
                "table": [{k: u.get(k) for k in ("full_name", "phone", "role", "is_active")} for u in users]}

    if topic == "staff":
        return {"role": "assistant",
                "content": "אני יכול לענות רק על דברים שקשורים אלייך: המשמרות שלך והמכירות שלך. "
                           "את טבלת המכירות של כל הצוות אפשר לראות במסך **דיווח מכירות**."}

    examples = ("- **המשמרות שלי** (למשל: \"מה השיבוצים שלי החודש?\", \"מתי אני עובד/ת בשבוע הבא?\")\n"
                "- **המכירות שלי** (למשל: \"כמה מכרתי השבוע?\", \"כמה מכרתי ב-12/11?\", \"כמה מכרתי מ-1/11 עד 15/11?\")\n"
                if not is_admin else
                "- **המלצה על סידור משמרות** (למשל: \"תמליץ לי על סידור לשבוע הקרוב\")\n"
                "- **נתוני מכירות** ו**מצבת עובדים**\n")
    return {"role": "assistant",
            "content": "אני יכול לעזור עם:\n" + examples +
                       "- **התקנת התראות לטלפון** (למשל: \"איך מתקינים התראות?\")\n"
                       "- **הוספת האפליקציה למסך הבית** (למשל: \"איך מורידים את האפליקציה?\")"}

# ------------------------------------------------------------
# המלצת סידור משמרות (למנהלת)
# כללים, לפי הסדר:
#   1. משבצים רק מי שהגיש זמינות לאותה משמרת.
#   2. הוגנות: קודם מי שיש לו הכי מעט משמרות השבוע.
#   3. מי שזמין רק למשמרת אחת באותו יום מקבל עדיפות על מי שזמין לשתיהן
#      (כך הגמישים פנויים להשלים משמרת אחרת).
#   4. עד משמרת אחת לעובד ביום; משמרת כפולה רק אם אין ברירה.
#   5. משמרת שעדיין חסרה - משלימים עם המנהלת (אם בחרה בזה), אחרת מסמנים "חסר".
# שיבוצים שכבר קיימים (טיוטה / נשלח) נספרים ולא משתנים.
# ------------------------------------------------------------
def build_schedule_proposal(days, rows, admin, per_shift, admin_fill):
    slots = [(d, k) for d in days for k in SHIFT_TYPES]
    names = {r["user_id"]: r["full_name"] for r in rows}
    if admin:
        names[admin["user_id"]] = admin["full_name"]

    existing = {s: [r["user_id"] for r in rows if r["shift_date"] == s[0].isoformat()
                    and r["shift_type"] == s[1] and r["status"] in ("planned", "active")] for s in slots}
    avail = {s: [r["user_id"] for r in rows if r["shift_date"] == s[0].isoformat()
                 and r["shift_type"] == s[1] and r["status"] == "available"] for s in slots}
    count = {}
    for s in slots:
        for u in existing[s]:
            count[u] = count.get(u, 0) + 1
    day_taken = {(d, u) for (d, k), us in existing.items() for u in us}
    flex = {}
    for (d, k), us in avail.items():
        for u in us:
            flex[(d, u)] = flex.get((d, u), 0) + 1

    new = {s: [] for s in slots}
    for allow_double in (False, True):
        for s in slots:
            d = s[0]
            need = per_shift - len(existing[s]) - len(new[s])
            if need <= 0:
                continue
            cands = [u for u in avail[s] if u not in new[s] and u not in existing[s]
                     and (allow_double or (d, u) not in day_taken)]
            cands.sort(key=lambda u: (count.get(u, 0), flex.get((d, u), 0), names.get(u, "")))
            for u in cands[:need]:
                new[s].append(u)
                count[u] = count.get(u, 0) + 1
                day_taken.add((d, u))

    items, gaps = [], []
    for s in slots:
        for u in new[s]:
            items.append({"user_id": u, "name": names.get(u, "?"), "date": s[0], "type": s[1], "source": "availability"})
        missing = per_shift - len(existing[s]) - len(new[s])
        if missing > 0 and admin_fill and admin and admin["user_id"] not in existing[s] + new[s]:
            items.append({"user_id": admin["user_id"], "name": admin["full_name"], "date": s[0],
                          "type": s[1], "source": "admin"})
            missing -= 1
        if missing > 0:
            gaps.append((s, missing))

    # טבלה לתצוגה: יום x משמרת
    table = []
    for d in days:
        row = {"יום": day_label(d)}
        for k, t in SHIFT_TYPES.items():
            cell = []
            for r in rows:
                if r["shift_date"] == d.isoformat() and r["shift_type"] == k and r["status"] in ("planned", "active"):
                    cell.append(("✅ " if r["status"] == "active" else "📝 ") + r["full_name"])
            for it in items:
                if it["date"] == d and it["type"] == k:
                    cell.append(("👑 " if it["source"] == "admin" else "✋ ") + it["name"])
            missing = next((m for (s, m) in gaps if s == (d, k)), 0)
            if missing:
                cell.append(f"⚠️ חסר {missing}")
            row[t["label"]] = ", ".join(cell) or "—"
        table.append(row)
    return items, gaps, pd.DataFrame(table).set_index("יום")

def render_schedule_proposal(week_start_iso, user, msgs):
    start = date.fromisoformat(week_start_iso)
    days = [start + timedelta(days=i) for i in range(7)]
    days = [d for d in days if d >= today_il()]
    if not days:
        st.caption("השבוע הזה כבר עבר.")
        return
    rows = call("get_week_shifts", {"week_start": start.isoformat()}, error="שגיאה בטעינת המשמרות") or []

    with st.container(horizontal=True, vertical_alignment="bottom"):
        per_shift = st.number_input("כמה עובדים בכל משמרת", min_value=1, max_value=5, value=1, key="prop_n")
        admin_fill = st.toggle("להשלים חוסרים איתי (מנהלת)", value=True, key="prop_fill")

    items, gaps, table = build_schedule_proposal(days, rows, user, int(per_shift), admin_fill)
    st.table(table)
    st.caption("✋ לפי זמינות שהעובד שלח · 👑 השלמה שלך · 📝 טיוטה קיימת · ✅ כבר נשלח · ⚠️ חסר")
    if gaps:
        st.warning("חסרים עובדים ב-" + ", ".join(
            f"{day_label(d)} {SHIFT_TYPES[k]['label']}" for (d, k), _ in gaps), icon=":material/warning:")
    if not items:
        st.info("אין שיבוצים חדשים להציע - אין זמינויות פתוחות או שהכל כבר משובץ.")
        return

    with st.container(horizontal=True):
        if st.button(f"✓ אישור ההצעה ({len(items)} שיבוצים) - נשמר כטיוטה", type="primary",
                     key=f"approve_{week_start_iso}"):
            ok = all(assign_shift(it["user_id"], it["date"], it["type"]) is not FAILED for it in items)
            if ok:
                msgs.append({"role": "assistant",
                             "content": "✅ ההצעה נשמרה כ**טיוטה**. העובדים עוד לא רואים אותה. "
                                        "אפשר לשנות במסך **משמרות**, ואז ללחוץ **שליחת שיבוצים לעובדים**."})
                st.rerun()
        if st.button("מעבר ללוח השיבוץ", icon=":material/edit_calendar:", key=f"goto_{week_start_iso}"):
            st.session_state.goto = "משמרות"
            st.session_state.week_offset = (start - week_start_for(today_il())).days // 7
            st.rerun()

def agent_screen(user):
    is_admin = user["role"] == "admin"
    st.title("🤖 סוכן חכם")

    dash = {}
    if is_admin:
        dash = call("admin_dashboard_data", error="שגיאה בטעינת הנתונים") or {}
        sales_data = dash.get("sales") or []
        total_sales = sum(float(item["total_amount"] or 0) for item in sales_data)
        with st.container(horizontal=True):
            st.metric("סך הכנסות מדווחות", f"₪{total_sales:,.2f}", border=True)
            st.metric("עובדים רשומים", len(dash.get("users") or []), border=True)
            st.metric("משמרות קרובות", dash.get("active_shifts") or 0, border=True)

    if "agent_msgs" not in st.session_state:
        st.session_state.agent_msgs = [{
            "role": "assistant",
            "content": f"שלום {user['full_name']}! במה אפשר לעזור? אפשר לשאול למשל "
                       "\"איך מתקינים התראות?\" או \"איך מורידים את האפליקציה לטלפון?\"",
        }]
    msgs = st.session_state.agent_msgs

    # שאלות מהירות
    with st.container(horizontal=True):
        quick = None
        if st.button("התקנת התראות", icon=":material/notifications:"):
            quick = "איך מתקינים את ההתראות לטלפון?"
        if st.button("הוספת האפליקציה לטלפון", icon=":material/install_mobile:"):
            quick = "איך מורידים את האפליקציה לטלפון?"

    for i, m in enumerate(msgs):
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("table"):
                st.dataframe(pd.DataFrame(m["table"]), hide_index=True, alt="נתונים מהסוכן")
            # הצעת סידור - אינטראקטיבית רק בהודעה האחרונה
            if m.get("proposal") and i == len(msgs) - 1 and is_admin:
                render_schedule_proposal(m["proposal"], user, msgs)
            # כפתורי בחירת טלפון - רק בהודעה האחרונה שעוד לא נענתה
            if m.get("ask_device") and i == len(msgs) - 1:
                with st.container(horizontal=True):
                    for key, label in DEVICES.items():
                        icon = ":material/phone_iphone:" if key == "iphone" else ":material/android:"
                        if st.button(label, key=f"device_{i}_{key}", icon=icon, type="primary"):
                            msgs.append({"role": "user", "content": label})
                            msgs.append(guide_message(m["ask_device"], key))
                            st.rerun()

    question = st.chat_input("כתבו שאלה...") or quick
    if question:
        msgs.append({"role": "user", "content": question})
        msgs.append(agent_answer(question, user, dash))
        st.rerun()


# ============================================================
# לוח בקרה והתראות
# ============================================================
def notifications_banner(user):
    n = call("get_notifications", error="שגיאה בטעינת ההתראות") or {}
    msgs = []
    if n.get("new_shifts"):
        msgs.append(f"שובצת ל-**{n['new_shifts']}** משמרות חדשות")
    if n.get("new_tasks"):
        msgs.append(f"קיבלת **{n['new_tasks']}** משימות חדשות")
    if n.get("new_availability"):
        msgs.append(f"**{n['new_availability']}** הגשות זמינות חדשות מעובדים")
    if n.get("done_tasks"):
        msgs.append(f"**{n['done_tasks']}** משימות סומנו כבוצעו (פרטים במסך **משימות** ← בוצעו)")
    if not msgs:
        return
    with st.container(border=True):
        st.markdown(":material/notifications_active: **התראות חדשות**  \n" +
                    "  \n".join(f"• {m}" for m in msgs))
        if st.button("ראיתי", icon=":material/done_all:", type="primary"):
            call("mark_notifications_seen", error="שגיאה בעדכון ההתראות")
            st.rerun()

# ============================================================
# התראות קבועות (במסך "ניהול עובדים")
# הכללים נשמרים בטבלה notification_rules, ו-pg_cron ב-Supabase
# שולח אותם כל 5 דקות - גם כשאף אחד לא מחובר לאפליקציה.
# ============================================================
TRIGGERS = {
    "shift_end": "בסוף משמרת",
    "shift_start": "בתחילת משמרת",
    "daily": "כל יום",
    "weekly": "כל שבוע",
}
TARGETS = {
    "shift_workers": "מי שמשובץ/ת למשמרת",
    "all_employees": "כל העובדים",
    "admins": "המנהלות",
}
SALES_REMINDER = {
    "p_title": "עדכון מכירות",
    "p_message": "היי {שם}, משמרת ה{משמרת} הסתיימה. אל תשכח/י לעדכן את המכירות באפליקציה 💰",
    "p_trigger_type": "shift_end", "p_offset_minutes": 0, "p_shift_type": None,
    "p_send_time": None, "p_weekday": None, "p_target": "shift_workers",
}

def describe_rule(r):
    """תיאור הכלל בעברית, למשל: 'בסוף משמרת בוקר, 10 דק' אחרי · ל: מי שמשובץ/ת למשמרת'."""
    t = r["trigger_type"]
    if t in ("shift_start", "shift_end"):
        when = TRIGGERS[t]
        if r.get("shift_type"):
            when += " " + SHIFT_TYPES.get(r["shift_type"], {}).get("label", r["shift_type"])
        off = r.get("offset_minutes") or 0
        if off:
            when += f", {abs(off)} דק' {'אחרי' if off > 0 else 'לפני'}"
    elif t == "daily":
        when = f"כל יום ב-{r.get('send_time')}"
    else:
        when = f"כל יום {HE_DAYS[r.get('weekday') or 0]} ב-{r.get('send_time')}"
    return f"{when} · ל: {TARGETS.get(r['target'], r['target'])}"

def preview_text(text, user, shift_type=None):
    shift_label = SHIFT_TYPES.get(shift_type or "morning", {}).get("label", "בוקר")
    return (text.replace("{שם}", user["full_name"]).replace("{משמרת}", shift_label)
                .replace("{תאריך}", today_il().strftime("%d/%m")))

def _toggle_rule(rule_id, key):
    """נקרא כשמשנים את המתג 'פעילה' של כלל."""
    call("admin_set_rule_active", {"p_rule_id": rule_id, "p_active": st.session_state[key]},
         error="שגיאה בעדכון")

def recurring_rules_section(user):
    st.subheader("התראות קבועות")
    st.caption("תזכורות שנשלחות לבד לטלפון (ntfy), גם כשאף אחד לא מחובר. "
               "בטקסט אפשר לכתוב {שם}, {משמרת}, {תאריך} - והם יוחלפו אוטומטית.")

    rules = call("admin_list_rules", error="שגיאה בטעינת ההתראות הקבועות")
    if rules is FAILED:
        st.info("כדי להשתמש בהתראות קבועות צריך להריץ ב-Supabase את notification_rules.sql.")
        return
    rules = rules or []

    if not any(r["trigger_type"] == "shift_end" and r["target"] == "shift_workers" for r in rules):
        if st.button("הוספה מהירה: תזכורת עדכון מכירות בסוף כל משמרת",
                     icon=":material/bolt:", type="primary"):
            if call("admin_create_rule", SALES_REMINDER, error="שגיאה ביצירת ההתראה") is not FAILED:
                st.toast("התזכורת נוספה.", icon=":material/check:")
                st.rerun()

    if not rules:
        st.caption("אין עדיין התראות קבועות.")
    for r in rules:
        with st.container(border=True):
            st.markdown(f"**{r['title']}**  \n:gray[{describe_rule(r)}]")
            st.caption(r["message"])
            with st.container(horizontal=True, vertical_alignment="center"):
                st.toggle("פעילה", value=bool(r["is_active"]), key=f"rule_on_{r['id']}",
                          on_change=_toggle_rule, args=(r["id"], f"rule_on_{r['id']}"))
                if st.button("שלח לי בדיקה", key=f"rule_test_{r['id']}", icon=":material/send:"):
                    s = call("get_my_notification_settings", error="שגיאה") or {}
                    if s.get("notify_push") and s.get("topic"):
                        st_label = r.get("shift_type")
                        if push(s["topic"], preview_text(r["title"], user, st_label),
                                preview_text(r["message"], user, st_label), tags=["alarm_clock"]):
                            st.toast("נשלחה בדיקה לטלפון שלך.", icon=":material/check:")
                    else:
                        st.warning("ההתראות לטלפון שלך כבויות או לא מחוברות (מסך התראות).")
                if st.button("מחיקה", key=f"rule_del_{r['id']}", icon=":material/delete:", type="tertiary"):
                    if call("admin_delete_rule", {"p_rule_id": r["id"]}, error="שגיאה במחיקה") is not FAILED:
                        st.rerun()

    with st.expander("התראה קבועה חדשה", icon=":material/add_alert:"):
        title = st.text_input("כותרת", key="nr_title")
        message = st.text_area("טקסט ההתראה", key="nr_msg",
                               placeholder="למשל: היי {שם}, אל תשכח/י לעדכן מכירות")
        trigger = st.segmented_control("מתי", list(TRIGGERS), format_func=TRIGGERS.get,
                                       default="shift_end", required=True, key="nr_trigger")
        shift_type, offset, send_time, weekday = None, 0, None, None
        if trigger in ("shift_start", "shift_end"):
            shift_opts = {"": "כל המשמרות", **{k: v["label"] for k, v in SHIFT_TYPES.items()}}
            shift_type = st.segmented_control("איזו משמרת", list(shift_opts), format_func=shift_opts.get,
                                              default="", required=True, key="nr_shift") or None
            with st.container(horizontal=True, vertical_alignment="bottom"):
                minutes = st.number_input("דקות", min_value=0, max_value=600, step=5, value=0, key="nr_min")
                direction = st.segmented_control("כיוון", ["אחרי", "לפני"], default="אחרי", required=True,
                                                 key="nr_dir", label_visibility="collapsed")
            offset = int(minutes) * (1 if direction == "אחרי" else -1)
            target_opts = ["shift_workers", "admins"]
        else:
            send_time = st.time_input("שעה", value=time(9, 0), key="nr_time")
            if trigger == "weekly":
                weekday = st.segmented_control("יום", list(range(7)), format_func=lambda i: HE_DAYS[i],
                                               default=0, required=True, key="nr_day")
            target_opts = list(TARGETS)
        target = st.segmented_control("למי", target_opts, format_func=TARGETS.get,
                                      default=target_opts[0], required=True, key="nr_target")

        if st.button("שמירת ההתראה", type="primary", icon=":material/save:", width="stretch"):
            if not title.strip() or not message.strip():
                st.warning("חובה למלא כותרת וטקסט.")
            elif call("admin_create_rule", {
                "p_title": title, "p_message": message, "p_trigger_type": trigger,
                "p_offset_minutes": offset, "p_shift_type": shift_type,
                "p_send_time": send_time.strftime("%H:%M") if send_time else None,
                "p_weekday": weekday, "p_target": target,
            }, error="שגיאה ביצירת ההתראה") is not FAILED:
                for k in ("nr_title", "nr_msg"):
                    st.session_state.pop(k, None)
                st.toast("ההתראה הקבועה נשמרה.", icon=":material/check:")
                st.rerun()


def dashboard_screen(user):
    is_admin = user["role"] == "admin"
    st.title(f"שלום {user['full_name']} 👋")
    today = today_il()
    shifts = call("get_week_shifts", {"week_start": week_start_for(today).isoformat()},
                  error="שגיאה בטעינת המשמרות") or []
    tasks = call("get_tasks", error="שגיאה בטעינת המשימות") or []
    open_tasks = [t for t in tasks if (t.get("status") or "open") == "open"]
    upcoming = [s for s in shifts
                if s["status"] == "active" and s["shift_date"] >= today.isoformat()]

    with st.container(horizontal=True):
        if is_admin:
            today_count = len([s for s in upcoming if s["shift_date"] == today.isoformat()])
            pending = len([s for s in shifts if s["status"] == "available"
                           and s["shift_date"] >= today.isoformat()])
            st.metric("משמרות היום", today_count, border=True)
            st.metric("זמינויות ממתינות", pending, border=True)
            st.metric("משימות פתוחות", len(open_tasks), border=True)
        else:
            st.metric("המשמרות שלי השבוע", len(upcoming), border=True)
            st.metric("משימות פתוחות", len(open_tasks), border=True)

    if not is_admin:
        st.subheader("המשמרות הקרובות שלי")
        if not upcoming:
            st.caption("אין משמרות קרובות השבוע.")
        for s in upcoming:
            label = SHIFT_TYPES.get(s["shift_type"], {}).get("label", s["shift_type"])
            st.markdown(f":blue-badge[{day_label(date.fromisoformat(s['shift_date']))}] "
                        f"{label} {str(s['start_time'])[:5]}–{str(s['end_time'])[:5]}")


# ============================================================
# מסך התחברות
# ============================================================
# ניהול מצב התחברות (Session State)
if "user" not in st.session_state:
    st.session_state.user = None

def login_screen():
    show_logo()

    st.title("התחברות למערכת ניהול חנות #TOYS")

    phone_input = st.text_input("הקלידי מספר טלפון:")

    if st.button("המשך"):
        clean_phone = phone_input.strip()
        if not clean_phone:
            st.warning("נא להזין מספר טלפון.")
            return

        try:
            res = supabase.rpc("check_phone_status", {"phone_input": clean_phone}).execute()
            data = res.data

            if not data or data.get("status") == "not_found":
                st.error("מספר הטלפון אינו מורשה במערכת או שאינו פעיל.")
            elif data.get("status") == "needs_password":
                st.session_state.temp_user = data
                st.session_state.step = "set_password"
                st.rerun()
            elif data.get("status") == "registered":
                st.session_state.temp_user = data
                st.session_state.step = "enter_password"
                st.rerun()
        except Exception as e:
            st.error(f"שגיאה בהתחברות: {e}")

    if "step" in st.session_state and st.session_state.step == "set_password":
        st.info(f"שלום {st.session_state.temp_user['full_name']}! זוהי כניסתך הראשונה. נא להגדיר סיסמה:")
        new_pwd = st.text_input("בחר סיסמה חדשה:", type="password")
        if st.button("הגדר סיסמה והתחבר"):
            try:
                auth_res = supabase.auth.sign_up({
                    "email": auth_email(st.session_state.temp_user['user_id']),
                    "password": new_pwd
                })
                if auth_res.user:
                    supabase.rpc("complete_registration", {
                        "p_user_id": st.session_state.temp_user['user_id']
                    }).execute()

                    st.success("הסיסמה הוגדרה בהצלחה! מתחבר...")
                    st.session_state.user = load_user_profile(st.session_state.temp_user)
                    del st.session_state.step
                    st.rerun()
            except Exception as e:
                st.error(f"שגיאה בהגדרת סיסמה: {e}")

    if "step" in st.session_state and st.session_state.step == "enter_password":
        st.info(f"שלום {st.session_state.temp_user['full_name']}! נא להקליד סיסמה:")
        pwd = st.text_input("סיסמה:", type="password", key="login_pwd")
        if st.button("התחבר למערכת"):
            try:
                auth_res = supabase.auth.sign_in_with_password({
                    "email": auth_email(st.session_state.temp_user['user_id']),
                    "password": pwd
                })
                if auth_res.user:
                    st.session_state.user = load_user_profile(st.session_state.temp_user)
                    del st.session_state.step
                    st.rerun()
            except Exception as e:
                st.error(f"סיסמה שגויה או שגיאה בהתחברות. ({e})")


# ============================================================
# האפליקציה
# ============================================================
if not st.session_state.user:
    login_screen()
elif st.session_state.user.get("must_change_password"):
    change_password_screen()
else:
    user = st.session_state.user
    is_admin = user['role'] == 'admin'

    # כותרת עליונה: לוגו, שלום ותפקיד, כפתור התנתקות.
    # הכל בעמוד הראשי ולא בסרגל הצדי, כי בטלפון הסרגל הצדי מוסתר.
    with st.container(horizontal=True, vertical_alignment="center"):
        try:
            st.image("logo.png", width=90)
        except Exception as e:
            st.caption(f"הלוגו לא נטען: {e}")
        st.markdown(f"שלום, **{user['full_name']}**  \n"
                    f"{':violet-badge[מנהל/ת]' if is_admin else ':blue-badge[עובד/ת]'}")
        if st.button("התנתק", icon=":material/logout:"):
            try:
                supabase.auth.sign_out()
            except Exception:
                pass
            st.session_state.user = None
            st.rerun()

    # מעבר למסך אחר מתוך כפתור (למשל "מעבר ללוח השיבוץ" אצל הסוכן)
    if "goto" in st.session_state:
        st.session_state.nav = st.session_state.pop("goto")

    # תפריט ניווט בכפתורים, נשבר לשורות בטלפון
    if is_admin:
        menu = {
            "לוח בקרה": ":material/dashboard:",
            "משמרות": ":material/calendar_month:",
            "סידור שבועי": ":material/calendar_view_week:",
            "משימות": ":material/task_alt:",
            "מכירות": ":material/payments:",
            "ניהול עובדים": ":material/group:",
            "סוכן AI חכם": ":material/smart_toy:",
            "התראות": ":material/notifications:",
        }
    else:
        menu = {
            "לוח בקרה": ":material/dashboard:",
            "משמרות": ":material/calendar_month:",
            "משימות": ":material/task_alt:",
            "דיווח מכירות": ":material/payments:",
            "התראות": ":material/notifications:",
            "סוכן AI חכם": ":material/smart_toy:",
        }

    if st.session_state.get("nav") not in menu:
        st.session_state.nav = "לוח בקרה"
    choice = st.pills(
        "תפריט ניווט",
        list(menu.keys()),
        format_func=lambda name: f"{menu[name]} {name}",
        required=True,
        key="nav",
        label_visibility="collapsed",
    )

    notifications_banner(user)
    st.divider()

    if choice == "לוח בקרה":
        dashboard_screen(user)

    elif choice == "משמרות":
        shifts_screen(user)

    elif choice == "סידור שבועי" and is_admin:
        weekly_schedule_screen()

    elif choice == "משימות":
        tasks_screen(user)

    elif choice == "התראות":
        phone_notifications_screen(user)

    elif choice == "דיווח מכירות" and not is_admin:
        sales_report_screen(user)

    elif choice == "מכירות" and is_admin:
        sales_admin_screen()

    elif choice == "ניהול עובדים" and is_admin:
        st.title("ניהול עובדים והרשאות")

        with st.form("add_employee"):
            st.subheader("הוספת עובד חדש")
            emp_name = st.text_input("שם מלא")
            emp_phone = st.text_input("מספר טלפון")
            emp_role = st.selectbox("תפקיד", ["employee", "admin"],
                                    format_func=lambda r: "מנהל/ת" if r == "admin" else "עובד/ת")

            submitted = st.form_submit_button("הוסף עובד", type="primary")
            if submitted:
                if emp_name and emp_phone:
                    if call("admin_create_user", {
                        "emp_name": emp_name,
                        "emp_phone": emp_phone,
                        "emp_role": emp_role
                    }, error="שגיאה בהוספת עובד") is not FAILED:
                        st.success(f"העובד {emp_name} נוסף בהצלחה למערכת!")
                else:
                    st.warning("נא למלא את כל השדות.")

        st.markdown("---")
        st.subheader("איפוס סיסמה לעובד")
        st.caption("קובעים סיסמה זמנית ומוסרים אותה לעובד. בכניסה הבאה הוא יחויב לבחור סיסמה חדשה.")
        employees = call("admin_list_users", error="שגיאה בטעינת רשימת העובדים") or []

        registered = [emp for emp in employees if emp.get("is_registered")]
        if not registered:
            st.info("אין עדיין עובדים שהגדירו סיסמה.")
        else:
            with st.form("reset_password"):
                labels = {f"{emp['full_name']} ({emp['phone']})": emp["id"] for emp in registered}
                chosen = st.selectbox("בחירת עובד", list(labels.keys()))
                temp_pwd = st.text_input("סיסמה זמנית (לפחות 6 תווים)", type="password")
                if st.form_submit_button("אפס סיסמה"):
                    if len(temp_pwd) < 6:
                        st.warning("הסיסמה הזמנית חייבת להכיל לפחות 6 תווים.")
                    elif call("admin_set_temp_password", {
                        "target_user_id": labels[chosen],
                        "temp_password": temp_pwd
                    }, error="שגיאה באיפוס הסיסמה") is not FAILED:
                        st.success(f"הסיסמה של {chosen} אופסה. מסרי לעובד את הסיסמה הזמנית.")

        st.markdown("---")
        recurring_rules_section(user)

    elif choice == "סוכן AI חכם":
        agent_screen(user)
