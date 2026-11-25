import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime

# הגדרת עיצוב עמוד ואייקון בדפדפן
st.set_page_config(page_title="#TOYS - ניהול חנות", page_icon="🧸", layout="wide")

# חיבור ל-Supabase מתוך ה-Secrets של Streamlit.
# לכל משתמש (כל לשונית דפדפן) חיבור משלו, שמור ב-session_state.
# אם החיבור היה משותף (cache_resource), כל המשתמשים היו עובדים מול ה-DB
# בזהות של מי שהתחבר אחרון.
def get_connection() -> Client:
    if "sb" not in st.session_state:
        st.session_state.sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    return st.session_state.sb

supabase: Client = get_connection()

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

def show_logo(width=250):
    try:
        left, center, right = st.columns([1, 1, 1])
        with center:
            st.image("logo.png", width=width)
    except Exception:
        pass

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
                    supabase.table("users").update({
                        "is_registered": True,
                        "auth_id": auth_res.user.id
                    }).eq("id", st.session_state.temp_user['user_id']).execute()
                    
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

if not st.session_state.user:
    login_screen()
elif st.session_state.user.get("must_change_password"):
    change_password_screen()
else:
    user = st.session_state.user
    
    try:
        st.sidebar.image("logo.png", width=200)
    except Exception as e:
        st.sidebar.caption(f"הלוגו לא נטען: {e}")
        
    st.sidebar.write(f"שלום, **{user['full_name']}**")
    st.sidebar.write(f"תפקיד: {'מנהל (Admin)' if user['role']=='admin' else 'עובד'}")
    
    if st.sidebar.button("התנתק"):
        try:
            supabase.auth.sign_out()
        except Exception:
            pass
        st.session_state.user = None
        st.rerun()

    menu = ["לוח בקרה", "משמרות", "משימות", "דיווח מכירות"]
    if user['role'] == 'admin':
        menu.append("ניהול עובדים (Admin)")
        menu.append("סוכן AI חכם")
        
    choice = st.sidebar.selectbox("תפריט ניווט", menu)

    if choice == "לוח בקרה":
        st.title("📊 ברוכים הבאים למערכת ניהול החנות #TOYS")
        st.write("כאן תוכלו לראות סיכומים מהירים, משימות פתוחות ועדכונים יומיים.")

    elif choice == "משמרות":
        st.title("📅 סידור עבודה המשמרות")
        st.write("ניהול וצפייה במשמרות השבועיות.")

    elif choice == "משימות":
        st.title("📝 משימות ומטלות")
        st.write("מעקב אחר משימות רגילות ומתוזמנות.")

    elif choice == "דיווח מכירות":
        st.title("💰 דיווח מכירות יומי")
        sales_amount = st.number_input("סך מכירות במשמרת (₪)", min_value=0.0, step=10.0)
        trans_count = st.number_input("מספר טרנזקציות/לקוחות", min_value=0, step=1)
        notes = st.text_area("הערות נוספות")
        
        if st.button("שמור דיווח"):
            try:
                supabase.table("sales").upsert({
                    "user_id": user['user_id'],
                    "sale_date": str(datetime.now().date()),
                    "total_amount": sales_amount,
                    "transactions_count": trans_count,
                    "notes": notes
                }).execute()
                st.success("הדיווח נשמר בהצלחה!")
            except Exception as e:
                st.error(f"שגיאה בשמירת הדיווח: {e}")

    elif choice == "ניהול עובדים (Admin)" and user['role'] == 'admin':
        st.title("👥 ניהול עובדים והרשאות")
        
        with st.form("add_employee"):
            st.subheader("הוספת עובד חדש")
            emp_name = st.text_input("שם מלא")
            emp_phone = st.text_input("מספר טלפון")
            emp_role = st.selectbox("תפקיד", ["employee", "admin"])
            
            submitted = st.form_submit_button("הוסף עובד")
            if submitted:
                if emp_name and emp_phone:
                    try:
                        supabase.rpc("admin_create_user", {
                            "emp_name": emp_name,
                            "emp_phone": emp_phone,
                            "emp_role": emp_role
                        }).execute()
                        st.success(f"העובד {emp_name} נוסף בהצלחה למערכת!")
                    except Exception as e:
                        st.error(f"שגיאה בהוספת עובד: {e}")
                else:
                    st.warning("נא למלא את כל השדות.")

        st.markdown("---")
        st.subheader("איפוס סיסמה לעובד")
        st.caption("קובעים סיסמה זמנית ומוסרים אותה לעובד. בכניסה הבאה הוא יחויב לבחור סיסמה חדשה.")
        try:
            employees = supabase.rpc("admin_list_users").execute().data or []
        except Exception as e:
            employees = []
            st.error(f"שגיאה בטעינת רשימת העובדים: {e}")

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
                    else:
                        try:
                            supabase.rpc("admin_set_temp_password", {
                                "target_user_id": labels[chosen],
                                "temp_password": temp_pwd
                            }).execute()
                            st.success(f"הסיסמה של {chosen} אופסה. מסרי לעובד את הסיסמה הזמנית.")
                        except Exception as e:
                            st.error(f"שגיאה באיפוס הסיסמה: {e}")

    elif choice == "סוכן AI חכם" and user['role'] == 'admin':
        st.title("🤖 סוכן ניהול חכם (AI)")
        st.write("הסוכן האישי שלך לניתוח נתוני החנות, הפקת תובנות מכירות והמלצות לשיבוץ עובדים:")
        
        try:
            sales_res = supabase.table("sales").select("*").execute()
            sales_data = sales_res.data
            
            shifts_res = supabase.table("shifts").select("*").execute()
            shifts_data = shifts_res.data
            
            users_res = supabase.table("users").select("*").execute()
            users_data = users_res.data
        except Exception as e:
            sales_data, shifts_data, users_data = [], [], []

        col1, col2, col3 = st.columns(3)
        with col1:
            total_sales = sum(item['total_amount'] for item in sales_data) if sales_data else 0
            st.metric("סך הכנסות מדווחות", f"₪{total_sales:,.2f}")
        with col2:
            st.metric("עובדים רשומים", len(users_data) if users_data else 0)
        with col3:
            st.metric("משמרות פעילות", len(shifts_data) if shifts_data else 0)

        st.markdown("---")
        
        user_question = st.text_input("שאלי את הסוכן כל מה שתרצי על החנות (למשל: 'מה מצב המכירות?' או 'תנו לי המלצה לשיבוץ'):")
        
        if user_question:
            with st.spinner("הסוכן מנתח את נתוני החנות..."):
                q_lower = user_question.lower()
                
                if "מכירות" in q_lower or "כסף" in q_lower or "הכנסות" in q_lower or "דוחות" in q_lower:
                    if sales_data:
                        df_sales = pd.DataFrame(sales_data)
                        st.success("📊 **ניתוח נתוני מכירות:**")
                        st.dataframe(df_sales)
                        st.info(f"סך כל המחזורים במערכת עומד על ₪{total_sales:,.2f} לאורך {len(sales_data)} דיווחים.")
                    else:
                        st.warning("עדיין לא הוזנו דיווחי מכירות במערכת.")
                        
                elif "עובדים" in q_lower or "צוות" in q_lower or "שיבוץ" in q_lower or "משמרות" in q_lower:
                    if users_data:
                        df_users = pd.DataFrame(users_data)
                        st.success("👥 **מצבת כוח אדם ושיבוצים:**")
                        st.dataframe(df_users[['full_name', 'phone', 'role', 'is_active']])
                        st.info("💡 **המלצת הסוכן לשיבוץ:** מומלץ לוודא שלביקוש הגבוה בסופי השבוע יש לפחות 2 עובדים משובצים בכל משמרת לפחות 48 שעות מראש.")
                    else:
                        st.warning("אין עובדים רשומים כרגע מלבדך.")
                else:
                    st.success(f"🤖 **תשובת הסוכן:** ניתוח הנתונים המעודכן עבור החנות מראה על {len(users_data)} אנשי צוות ועל היקף פעילות יציב. מבדיקת השאלה שלך ('{user_question}'), ההמלצה המרכזית היא לעקוב מקרוב אחר דיווחי סוף המשמרת של העובדים ולוודא שכל המשימות מתבצעות בזמן.")