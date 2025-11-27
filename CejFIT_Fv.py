import os, csv, sqlite3, tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime

try:
    from tkcalendar import DateEntry
    TKCAL_AVAILABLE = True
except Exception:
    TKCAL_AVAILABLE = False

DB_FILENAME = 'progressive_overload.db'

PRELOADED_EXERCISES = [
    ("Squat", "Back", "Barbell", "Add Elevation", "Lower Back"),
    ("Pull Ups", "Back", "Bodyweight", "Slow and Controlled", "Vertical Mower"),
    ("Hammer Curls", "Biceps", "Dumbbells", "Add Back Pulling", "Brachioradialis"),
]

# ---------------- Database ----------------
class DatabaseManager:
    def __init__(self, db_filename=DB_FILENAME):
        self.conn = sqlite3.connect(db_filename)
        self.conn.execute('PRAGMA foreign_keys = ON')
        self.create_tables()
        self.ensure_columns()
        self.ensure_preloaded()

    def create_tables(self):
        c = self.conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                body_part TEXT,
                equipment TEXT,
                notes TEXT,
                subgroup TEXT
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exercise_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                notes TEXT,
                FOREIGN KEY (exercise_id) REFERENCES exercises(id) ON DELETE CASCADE
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                set_index INTEGER NOT NULL,
                weight REAL NOT NULL,
                reps INTEGER NOT NULL,
                rir INTEGER,
                unit TEXT DEFAULT 'lbs',
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        ''')
        self.conn.commit()

    def ensure_columns(self):
        c = self.conn.cursor()
        try:
            c.execute("ALTER TABLE sets ADD COLUMN rir INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE sets ADD COLUMN unit TEXT DEFAULT 'lbs'")
        except sqlite3.OperationalError:
            pass
        self.conn.commit()

    def ensure_preloaded(self):
        c = self.conn.cursor()
        c.execute('SELECT COUNT(*) FROM exercises')
        count = c.fetchone()[0]
        if count == 0:
            for ex in PRELOADED_EXERCISES:
                try:
                    c.execute(
                        'INSERT INTO exercises (name, body_part, equipment, notes, subgroup) VALUES (?, ?, ?, ?, ?)',
                        ex
                    )
                except sqlite3.IntegrityError:
                    pass
            self.conn.commit()

    # CRUD
    def add_exercise(self, name, body_part='', equipment='', notes='', subgroup=''):
        try:
            c = self.conn.cursor()
            c.execute('INSERT INTO exercises (name, body_part, equipment, notes, subgroup) VALUES (?, ?, ?, ?, ?)',
                      (name.strip(), body_part.strip(), equipment.strip(), notes.strip(), subgroup.strip()))
            self.conn.commit()
            return c.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError('Exercise already exists.')

    def get_exercises(self):
        c = self.conn.cursor()
        c.execute('''
            SELECT e.id, e.name, e.body_part, e.equipment, e.notes, e.subgroup,
                (SELECT MAX(date) FROM sessions s WHERE s.exercise_id = e.id) AS last_session
            FROM exercises e
            ORDER BY e.body_part COLLATE NOCASE, e.name COLLATE NOCASE
        ''')
        return c.fetchall()

    def update_exercise(self, id_, name, body_part, equipment, notes, subgroup):
        c = self.conn.cursor()
        c.execute('UPDATE exercises SET name=?, body_part=?, equipment=?, notes=?, subgroup=? WHERE id=?',
                  (name.strip(), body_part.strip(), equipment.strip(), notes.strip(), subgroup.strip(), id_))
        self.conn.commit()

    def delete_exercise(self, id_):
        c = self.conn.cursor()
        c.execute('DELETE FROM exercises WHERE id=?', (id_,))
        self.conn.commit()

    def add_session(self, exercise_id, date_str, notes=''):
        c = self.conn.cursor()
        c.execute('INSERT INTO sessions (exercise_id, date, notes) VALUES (?, ?, ?)',
                  (exercise_id, date_str, notes.strip()))
        self.conn.commit()
        return c.lastrowid

    def add_set(self, session_id, set_index, weight, reps, rir=None, unit='lbs'):
        c = self.conn.cursor()
        c.execute(
            'INSERT INTO sets (session_id, set_index, weight, reps, rir, unit) VALUES (?, ?, ?, ?, ?, ?)',
            (session_id, set_index, float(weight), int(reps),
             (int(rir) if rir is not None and str(rir).strip() != '' else None), unit))
        self.conn.commit()
        return c.lastrowid

    def get_sessions_for_exercise(self, exercise_id):
        c = self.conn.cursor()
        c.execute('SELECT id, date, notes FROM sessions WHERE exercise_id=? ORDER BY date DESC', (exercise_id,))
        return c.fetchall()

    def get_sets_for_session(self, session_id):
        c = self.conn.cursor()
        c.execute('SELECT set_index, weight, reps, rir, unit FROM sets WHERE session_id=? ORDER BY set_index',
                  (session_id,))
        return c.fetchall()

    def delete_session(self, session_id):
        c = self.conn.cursor()
        c.execute('DELETE FROM sessions WHERE id=?', (session_id,))
        self.conn.commit()

    def get_last_set_for_exercise(self, exercise_id):
        c = self.conn.cursor()
        c.execute('''
            SELECT sets.weight, sets.reps, sets.rir, sets.unit FROM sets
            JOIN sessions ON sets.session_id = sessions.id
            WHERE sessions.exercise_id = ?
            ORDER BY sessions.date DESC, sets.set_index DESC LIMIT 1
        ''', (exercise_id,))
        r = c.fetchone()
        return r if r else (None, None, None, None)

    def close(self):
        self.conn.close()


def safe_date_str(dt=None):
    if dt is None:
        dt = datetime.now()
    return dt.strftime('%Y-%m-%d')


def validate_exercise_name(name):
    if not name or not name.strip():
        raise ValueError('Exercise name cannot be empty.')
    if len(name.strip()) > 150:
        raise ValueError('Exercise name too long.')
    return name.strip()


def validate_weight_reps(w, r):
    try:
        weight = float(w)
        reps = int(r)
    except Exception:
        raise ValueError('Weight must be a number and reps an integer.')
    if weight < 0 or reps <= 0:
        raise ValueError('Invalid weight/reps.')
    return weight, reps


# ---------------- Tracker App ----------------
class TrackerApp:
    def __init__(self, root, db):
        self.root = root
        self.db = db

        # UI setup
        root.title("CejFIT")
        root.geometry("1220x760")
        root.configure(bg="#F6F3E6")
        root.minsize(980, 620)

        self.panel = "#FBF7F0"
        self.button = "#8E6F4F"
        self.button_active = "#7b5f45"

        self.hpan = tk.PanedWindow(root, orient='horizontal', sashwidth=6, bg=root['bg'])
        self.hpan.pack(fill='both', expand=True)

        # Left: exercise list
        self.left_frame = tk.Frame(self.hpan, bg=self.panel, padx=14, pady=12)
        self.hpan.add(self.left_frame, minsize=520)

        # Right: session data
        self.right_frame = tk.Frame(self.hpan, bg=root['bg'], padx=14, pady=12)
        self.hpan.add(self.right_frame, minsize=560)

        self.vpan = tk.PanedWindow(self.right_frame, orient='vertical', sashwidth=6, bg=root['bg'])
        self.vpan.pack(fill='both', expand=True)

        self.right_top = tk.Frame(self.vpan, bg=self.panel, padx=12, pady=12)
        self.right_bottom = tk.Frame(self.vpan, bg=self.panel, padx=12, pady=12)

        self.vpan.add(self.right_top, minsize=300)
        self.vpan.add(self.right_bottom, minsize=300)

        # Build UI
        self.set_buffer = []
        self.exercises = []

        self._build_left()
        self._build_right_top()
        self._build_right_bottom()

        self.refresh_exercises()
        self._set_initial_sashes()
        root.bind("<Configure>", self._on_root_configure)

    # --- UI Builders ---
    def _styled_btn(self, parent, text, cmd, width=None):
        b = tk.Button(parent, text=text, command=cmd, bg=self.button, fg='white',
                      activebackground=self.button_active, bd=0, padx=10, pady=6, relief='flat')
        if width:
            b.config(width=width)
        return b

    def _build_left(self):
        header = tk.Frame(self.left_frame, bg=self.panel)
        header.pack(fill='x', pady=(0, 8))
        tk.Label(header, text="Exercise Master List", bg=self.panel,
                 font=("Helvetica", 12, "bold")).pack(side='left')

        btns = tk.Frame(header, bg=self.panel)
        btns.pack(side='right')
        self._styled_btn(btns, "+ Add Exercise", self.add_exercise_dialog).pack(side='left', padx=6)
        tk.Button(btns, text="Delete", command=self.delete_exercise_confirm,
                  bg="#D95A5A", fg='white', bd=0, padx=10, pady=6).pack(side='left', padx=6)

        sframe = tk.Frame(self.left_frame, bg=self.panel)
        sframe.pack(fill='x', pady=(0, 8))

        self.search_var = tk.StringVar(value="Search Exercises here")
        self.sentry = ttk.Entry(sframe, textvariable=self.search_var)
        self.sentry.pack(fill='x', padx=(2,0))
        self.sentry.configure(foreground='grey')

        def _on_focus_in(e):
            if self.search_var.get() == "Search Exercises here":
                self.search_var.set('')
                try: self.sentry.configure(foreground='black')
                except: pass
        def _on_focus_out(e):
            if not self.search_var.get().strip():
                self.search_var.set("Search Exercises here")
                try: self.sentry.configure(foreground='grey')
                except: pass
        self.sentry.bind('<FocusIn>', _on_focus_in)
        self.sentry.bind('<FocusOut>', _on_focus_out)
        self.sentry.bind('<KeyRelease>', lambda e: self._apply_search())

        cols = ('name','last_session','body_part','equipment','notes','subgroup')
        fr = tk.Frame(self.left_frame, bg=self.panel)
        fr.pack(fill='both', expand=True)

        self.ex_table = ttk.Treeview(fr, columns=cols, show='headings', height=20)

        heads = {
            'name': 'Name',
            'last_session': 'Last Session',
            'body_part': 'Body Part',
            'equipment': 'Equipment',
            'notes': 'Notes',
            'subgroup': 'Subgroup'
        }
        widths = {
            'name': 220, 'last_session': 150, 'body_part': 120,
            'equipment': 120, 'notes': 300, 'subgroup': 220
        }

        for c in cols:
            self.ex_table.heading(c, text=heads[c])
            align = 'center' if c != 'notes' else 'w'
            self.ex_table.column(c, width=widths[c], anchor=align)
        vbar = ttk.Scrollbar(fr, orient='vertical', command=self.ex_table.yview)
        hbar = ttk.Scrollbar(fr, orient='horizontal', command=self.ex_table.xview)
        self.ex_table.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)
        self.ex_table.grid(row=0, column=0, sticky='nsew')
        vbar.grid(row=0, column=1, sticky='ns')
        hbar.grid(row=1, column=0, sticky='ew')
        fr.rowconfigure(0, weight=1); fr.columnconfigure(0, weight=1)

        self.ex_table.bind('<<TreeviewSelect>>', self.on_ex_select)
        self.ex_table.bind('<Double-1>', self.edit_exercise_dialog)

    # Top right UI
    def _build_right_top(self):
        self.sel_label = tk.Label(self.right_top, text="No exercise selected",
                                  bg=self.panel, font=("Helvetica",12,"bold"))
        self.sel_label.pack(anchor='w')

        container = tk.Frame(self.right_top, bg=self.panel)
        container.pack(fill='both', expand=True)

        row1 = tk.Frame(container, bg=self.panel)
        row1.pack(fill='x', pady=(4,6))

        leftcol = tk.Frame(row1, bg=self.panel)
        leftcol.pack(side='left', anchor='n')

        tk.Label(leftcol, text="Date", bg=self.panel).pack(anchor='w')
        if TKCAL_AVAILABLE:
            self.date_widget = DateEntry(leftcol, width=14, date_pattern='yyyy-mm-dd')
        else:
            self.date_widget = ttk.Entry(leftcol, width=14)
            self.date_widget.insert(0, safe_date_str())
        self.date_widget.pack(pady=(6,0))

        notescol = tk.Frame(row1, bg=self.panel)
        notescol.pack(side='left', fill='x', expand=True, padx=(12,0))

        tk.Label(notescol, text="Notes", bg=self.panel).pack(anchor='w')
        self.note_entry = ttk.Entry(notescol)
        self.note_entry.pack(fill='x', pady=(6,0))

        qr = tk.Frame(container, bg=self.panel)
        qr.pack(fill='x', pady=(8,0))

        tk.Label(qr, text='Weight', bg=self.panel).pack(side='left')
        self.q_weight = ttk.Entry(qr, width=8); self.q_weight.pack(side='left', padx=6)
        self.unit_var = tk.StringVar(value='lbs')
        ur = tk.Frame(qr, bg=self.panel); ur.pack(side='left', padx=(0,8))
        ttk.Radiobutton(ur, text='lbs', variable=self.unit_var, value='lbs').pack(side='left')
        ttk.Radiobutton(ur, text='kg', variable=self.unit_var, value='kg').pack(side='left')
        tk.Label(qr, text='Reps', bg=self.panel).pack(side='left', padx=(8,0))
        self.q_reps = ttk.Entry(qr, width=6); self.q_reps.pack(side='left', padx=6)
        tk.Label(qr, text='RIR', bg=self.panel).pack(side='left')
        self.q_rir = ttk.Entry(qr, width=4); self.q_rir.pack(side='left', padx=(6,8))
        self._styled_btn(qr, "Add Set", self.add_set_from_quick).pack(side='left', padx=6)

        tk.Label(container, text="Sets", bg=self.panel, font=("Helvetica",10,"bold")).pack(anchor='w', pady=(8,4))
        self.sets_tree = ttk.Treeview(container, columns=('idx','weight','reps','rir','unit'), show='headings', height=5)
        for c,h,w in [('idx','Set #',60), ('weight','Weight',100), ('reps','Rep Count',80), ('rir','RIR',60), ('unit','Unit',60)]:
            self.sets_tree.heading(c, text=h)
            self.sets_tree.column(c, width=w, anchor='center')
        self.sets_tree.pack(fill='both', expand=True)

        sc = tk.Frame(container, bg=self.panel)
        sc.pack(fill='x', pady=(8,0))
        self._styled_btn(sc, "Remove Set", self.remove_set).pack(side='left', padx=6)
        self._styled_btn(sc, "Save Session", self.save_session).pack(side='right', padx=6)

    # Bottom right UI
    def _build_right_bottom(self):
        tk.Label(self.right_bottom, text="Progress History", bg=self.panel, font=("Helvetica",11,"bold")).pack(anchor='w')
        self.sessions_tree = ttk.Treeview(self.right_bottom, columns=('date','weight','reps','rir','notes'), show='headings', height=8)
        specs = [('date','Session Date',120), ('weight','Weight',120), ('reps','Rep Count',80), ('rir','RIR',80), ('notes','Factor Notes',360)]
        for col,text,w in specs:
            self.sessions_tree.heading(col, text=text)
            anchor = 'w' if col == 'notes' else 'center'
            self.sessions_tree.column(col, width=w, anchor=anchor)
        self.sessions_tree.pack(fill='both', expand=True, pady=(6,8))
        self.sessions_tree.bind('<<TreeviewSelect>>', self.on_session_select)

        bf = tk.Frame(self.right_bottom, bg=self.panel)
        bf.pack(fill='x')
        self._styled_btn(bf, "Remove Session", self.delete_session_confirm).pack(side='left', padx=6)

    def _set_initial_sashes(self):
        self.root.update_idletasks()
        try:
            w = self.root.winfo_width()
            left_w = int(w * 0.55)
            self.hpan.sash_place(0, left_w, 0)
            h = self.root.winfo_height()
            top_h = int(h * 0.48)
            self.vpan.sash_place(0, 0, top_h)
        except Exception:
            pass

    def _on_root_configure(self, event):
        self._resize_master_columns()

    def _resize_master_columns(self):
        try:
            total_width = self.left_frame.winfo_width() - 30
            if total_width < 300:
                return
            proportions = {'name':0.20,'last_session':0.14,'body_part':0.12,'equipment':0.13,'notes':0.26,'subgroup':0.15}
            for col,p in proportions.items():
                self.ex_table.column(col, width=max(60, int(total_width * p)))
        except Exception:
            pass

    def refresh_exercises(self):
        for iid in self.ex_table.get_children():
            self.ex_table.delete(iid)
        self.exercises = self.db.get_exercises()
        for e in self.exercises:
            last = e[6] if len(e) > 6 and e[6] is not None else ''
            self.ex_table.insert('', 'end', iid=str(e[0]), values=(e[1], last, e[2] or '', e[3] or '', e[4] or '', e[5] or ''))
        children = self.ex_table.get_children()
        if children:
            self.ex_table.selection_set(children[0])
            self.ex_table.see(children[0])
            self.on_ex_select()

    def _apply_search(self):
        q = self.search_var.get().strip().lower()
        if q == "" or q == "search exercises here":
            for iid in self.ex_table.get_children():
                self.ex_table.reattach(iid, '', 'end')
            for e in self.exercises:
                iid = str(e[0])
                if iid in self.ex_table.get_children():
                    continue
                try:
                    self.ex_table.reattach(iid, '', 'end')
                except Exception:
                    pass
            return

        for iid in self.ex_table.get_children():
            vals = self.ex_table.item(iid, 'values')
            name = str(vals[0]).lower()
            bp = str(vals[2]).lower()
            notes = str(vals[4]).lower()
            subgroup = str(vals[5]).lower()
            if q in name or q in bp or q in notes or q in subgroup:
                self.ex_table.reattach(iid, '', 'end')
            else:
                self.ex_table.detach(iid)

    def get_selected_exercise(self):
        sel = self.ex_table.selection()
        if not sel:
            return None
        iid = int(sel[0])
        for e in self.exercises:
            if e[0] == iid:
                return e
        return None

    def on_ex_select(self, event=None):
        sel = self.get_selected_exercise()
        if not sel:
            self.sel_label.config(text="No exercise selected")
            return
        subgroup = sel[5] or sel[2] or ''
        self.sel_label.config(text=f"{sel[1]} ({subgroup})")

        for i in self.sessions_tree.get_children():
            self.sessions_tree.delete(i)
        self.sessions = self.db.get_sessions_for_exercise(sel[0])
        for s in self.sessions:
            sets = self.db.get_sets_for_session(s[0])
            if sets:
                first = sets[0]
                wdisp = f"{first[1]} {first[4] if len(first)>4 else ''}"
                rdisp = f"{first[2]}"
                rirdisp = f"{first[3] if first[3] is not None else ''}"
            else:
                wdisp = rdisp = rirdisp = ''
            self.sessions_tree.insert('', 'end', iid=str(s[0]), values=(s[1], wdisp, rdisp, rirdisp, s[2] or ''))
        self.set_buffer.clear()
        for i in self.sets_tree.get_children():
            self.sets_tree.delete(i)
        try:
            self.note_entry.delete(0, tk.END)
        except Exception:
            pass

    def add_set_from_quick(self):
        try:
            weight, reps = validate_weight_reps(self.q_weight.get(), self.q_reps.get())
        except Exception as e:
            messagebox.showerror('Invalid', str(e)); return
        rir_val = self.q_rir.get().strip()
        rir = int(rir_val) if rir_val != '' else None
        unit = self.unit_var.get()
        idx = len(self.set_buffer) + 1
        row = {'idx': idx, 'weight': weight, 'reps': reps, 'rir': rir, 'unit': unit}
        self.set_buffer.append(row)
        self.sets_tree.insert('', 'end', values=(idx, weight, reps, rir if rir is not None else '', unit))
        self.q_weight.delete(0, tk.END); self.q_reps.delete(0, tk.END); self.q_rir.delete(0, tk.END)

    def remove_set(self):
        sel = self.sets_tree.selection()
        if not sel:
            messagebox.showinfo('Select', 'Select a set to remove.'); return
        for s in sel:
            self.sets_tree.delete(s)
        newbuf = []
        for i,item in enumerate(self.sets_tree.get_children(), start=1):
            vals = list(self.sets_tree.item(item,'values'))
            weight = vals[1]; reps = vals[2]; rir = vals[3] if vals[3] != '' else None; unit = vals[4] if len(vals) > 4 else self.unit_var.get()
            newbuf.append({'idx': i, 'weight': weight, 'reps': reps, 'rir': rir, 'unit': unit})
            self.sets_tree.item(item, values=(i, weight, reps, rir if rir is not None else '', unit))
        self.set_buffer = newbuf

    def save_session(self):
        sel = self.get_selected_exercise()
        if not sel:
            messagebox.showinfo('Select', 'Select an exercise first.'); return
        if TKCAL_AVAILABLE:
            try:
                date_str = self.date_widget.get_date().strftime('%Y-%m-%d')
            except Exception:
                date_str = safe_date_str()
        else:
            date_str = self.date_widget.get().strip()
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except Exception:
            messagebox.showerror('Invalid date', 'Date must be YYYY-MM-DD'); return
        if not self.set_buffer:
            messagebox.showinfo('No sets', 'Add at least one set before saving.'); return
        notes = self.note_entry.get().strip() if self.note_entry else ''
        try:
            session_id = self.db.add_session(sel[0], date_str, notes)
            for s in self.set_buffer:
                self.db.add_set(session_id, s['idx'], s['weight'], s['reps'], s.get('rir'), s.get('unit','lbs'))
            messagebox.showinfo('Saved', 'Session saved.')
            self.set_buffer.clear()
            for i in self.sets_tree.get_children():
                self.sets_tree.delete(i)
            self.on_ex_select()
            self.refresh_exercises()
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def on_session_select(self, event=None):
        sel = self.sessions_tree.selection()
        if not sel:
            return
        sid = int(sel[0])
        for i in self.sets_tree.get_children():
            self.sets_tree.delete(i)
        sets = self.db.get_sets_for_session(sid)
        self.set_buffer = []
        for s in sets:
            idx, weight, reps, rir, unit = s
            self.sets_tree.insert('', 'end', values=(idx, weight, reps, rir if rir is not None else '', unit))
            self.set_buffer.append({'idx': idx, 'weight': weight, 'reps': reps, 'rir': rir, 'unit': unit})

    def delete_session_confirm(self):
        sel = self.sessions_tree.selection()
        if not sel:
            messagebox.showinfo('Select', 'Select session to delete.'); return
        sid = int(sel[0])
        if messagebox.askyesno('Confirm', 'Delete this session?'):
            try:
                self.db.delete_session(sid)
                self.on_ex_select()
                messagebox.showinfo('Deleted', 'Session removed.')
            except Exception as e:
                messagebox.showerror('Error', str(e))

    def add_exercise_dialog(self):
        d = ExerciseEditDialog(self.root, title='Add Exercise')
        if d.result:
            try:
                name = validate_exercise_name(d.result['name'])
                self.db.add_exercise(name, d.result.get('body_part',''), d.result.get('equipment',''),
                                     d.result.get('notes',''), d.result.get('subgroup',''))
                self.refresh_exercises()
            except Exception as e:
                messagebox.showerror('Error', str(e))

    def edit_exercise_dialog(self, event=None):
        sel = self.get_selected_exercise()
        if not sel:
            messagebox.showinfo('Select', 'Select an exercise to edit.'); return
        initial = {'name': sel[1], 'body_part': sel[2] or '', 'equipment': sel[3] or '',
                   'notes': sel[4] or '', 'subgroup': sel[5] or ''}
        d = ExerciseEditDialog(self.root, title='Edit Exercise', initial=initial)
        if d.result:
            try:
                name = validate_exercise_name(d.result['name'])
                self.db.update_exercise(sel[0], name, d.result.get('body_part',''),
                                        d.result.get('equipment',''), d.result.get('notes',''),
                                        d.result.get('subgroup',''))
                self.refresh_exercises()
            except Exception as e:
                messagebox.showerror('Error', str(e))

    def delete_exercise_confirm(self):
        sel = self.get_selected_exercise()
        if not sel:
            messagebox.showinfo('Select', 'Select an exercise to delete.'); return
        if messagebox.askyesno('Confirm', f'Delete exercise "{sel[1]}" and all sessions?'):
            try:
                self.db.delete_exercise(sel[0])
                self.refresh_exercises()
            except Exception as e:
                messagebox.showerror('Error', str(e))


# ---------------- Exercise edit dialog ----------------
class ExerciseEditDialog(simpledialog.Dialog):
    def __init__(self, parent, title=None, initial=None):
        self.initial = initial or {}
        super().__init__(parent, title=title)

    def body(self, master):
        ttk.Label(master, text='Exercise name:').grid(row=0, column=0, sticky='w')
        self.e_name = ttk.Entry(master, width=50); self.e_name.grid(row=0, column=1, pady=4)
        self.e_name.insert(0, self.initial.get('name',''))

        ttk.Label(master, text='Body Part:').grid(row=1, column=0, sticky='w')
        self.e_body = ttk.Entry(master, width=30); self.e_body.grid(row=1, column=1, pady=4)
        self.e_body.insert(0, self.initial.get('body_part',''))

        ttk.Label(master, text='Equipment:').grid(row=2, column=0, sticky='w')
        self.e_equip = ttk.Entry(master, width=30); self.e_equip.grid(row=2, column=1, pady=4)
        self.e_equip.insert(0, self.initial.get('equipment',''))

        ttk.Label(master, text='Subgroup:').grid(row=3, column=0, sticky='w')
        self.e_sub = ttk.Entry(master, width=30); self.e_sub.grid(row=3, column=1, pady=4)
        self.e_sub.insert(0, self.initial.get('subgroup',''))

        ttk.Label(master, text='Notes:').grid(row=4, column=0, sticky='nw')
        self.e_notes = tk.Text(master, width=40, height=4); self.e_notes.grid(row=4, column=1, pady=4)
        self.e_notes.insert('1.0', self.initial.get('notes',''))
        return self.e_name

    def apply(self):
        self.result = {
            'name': self.e_name.get().strip(),
            'body_part': self.e_body.get().strip(),
            'equipment': self.e_equip.get().strip(),
            'subgroup': self.e_sub.get().strip(),
            'notes': self.e_notes.get('1.0', tk.END).strip()
        }


# ---------------- MAIN ----------------
def main():
    root = tk.Tk()

    try:
        if os.path.exists("cejfit.ico"):
            root.iconbitmap("cejfit.ico")
    except Exception:
        pass

    db = DatabaseManager()
    app = TrackerApp(root, db)

    # Center window
    root.update_idletasks()
    w = root.winfo_width() or 1220
    h = root.winfo_height() or 760
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = max(0, int((sw - w) / 2))
    y = max(0, int((sh - h) / 2))
    root.geometry(f"{w}x{h}+{x}+{y}")

    root.protocol("WM_DELETE_WINDOW", lambda: (db.close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
