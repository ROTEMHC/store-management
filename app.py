import streamlit as st
from supabase import create_client, Client
import pandas as pd
from datetime import datetime

# הגדרת עיצוב עמוד ואייקון בדפדפן
st.set_page_config(page_title="#TOYS - ניהול חנות", page_icon="🧸", layout="wide")

# חיבור ל-Supabase מתוך ה-Secrets של Streamlit
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

# ניהול מצב התחברות (Session State)
if "user" not in st.session_state:
    st.session_state.user = None

def login_screen():
    # הצגת לוגו החנות במסך ההתחברות
    try:
        st.image("logo.png", width=250)
    except:
        pass
        
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
                    "email": f"{st.session_state.temp_user['user_id']}@store.local",
                    "password": new_pwd
                })
                if auth_res.user:
                    supabase.table("users").update({
                        "is_registered": True,
                        "auth_id": auth_res.user.id
                    }).eq("id", st.session_state.temp_user['user_id']).execute()
                    
                    st.success("הסיסמה הוגדרה בהצלחה! מתחבר...")
                    st.session_state.user = st.session_state.temp_user
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
                    "email": f"{st.session_state.temp_user['user_id']}@store.local",
                    "password": pwd
                })
                if auth_res.user:
                    st.session_state.user = st.session_state.temp_user
                    del st.session_state.step
                    st.rerun()
            except Exception as e:
                st.error("סיסמה שגויה או שגיאה בהתחברות.")

if not st.session_state.user:
    login_screen()
else:
    user = st.session_state.user
    
    # --- הוספת הלוגו לראש סרגל הצד (Sidebar) ---
    try:
        st.sidebar.image("logo.png", use_container_width=True)
    except:
        pass
        
    st.sidebar.write(f"שלום, **{user['full_name']}**")
    st.sidebar.write(f"תפקיד: {'מנהל (Admin)' if user['role']=='admin' else 'עובד'}")
    
    if st.sidebar.button("התנתק"):
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

    elif choice == "סוכן AI חכם" and user['role'] == 'admin':
        st.title("🤖 סוכן ניהול חכם (AI)")
        st.write("הסוכן האישי שלך לניתוח נתוני החנות, הפקת תובנות מכירות והמלצות לשיבוץ עובדים:")
        
        # שליפת נתונים מ-Supabase עבור הסוכן
        try:
            sales_res = supabase.table("sales").select("*").execute()
            sales_data = sales_res.data
            
            shifts_res = supabase.table("shifts").select("*").execute()
            shifts_data = shifts_res.data
            
            users_res = supabase.table("users").select("*").execute()
            users_data = users_res.data
        except Exception as e:
            sales_data, shifts_data, users_data = [], [], []

        # תצוגת סיכום מהיר למנהל
        col1, col2, col3 = st.columns(3)
        with col1:
            total_sales = sum(item['total_amount'] for item in sales_data) if sales_data else 0
            st.metric("סך הכנסות מדווחות", f"₪{total_sales:,.2f}")
        with col2:
            st.metric("עובדים רשומים", len(users_data) if users_data else 0)
        with col3:
            st.metric("משמרות פעילות", len(shifts_data) if shifts_data else 0)

        st.markdown("---")
        
        # אזור התשאול של הסוכן