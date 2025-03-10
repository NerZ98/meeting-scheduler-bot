import sqlite3
import os
import logging

class UserDatabase:
    """Database to store and query user information for meeting scheduling"""
    
    def __init__(self, db_path='users.db'):
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self._create_tables_if_not_exists()
    
    def _create_tables_if_not_exists(self):
        """Create the database tables if they don't exist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create users table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                department TEXT,
                job_title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Create index on names for faster lookups
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_names ON users(first_name, last_name)')
            
            conn.commit()
            conn.close()
            self.logger.info("Database tables created or already exist")
        except Exception as e:
            self.logger.error(f"Error creating database tables: {str(e)}")
            raise
    
    def add_user(self, first_name, last_name, email, department=None, job_title=None):
        """Add a new user to the database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                'INSERT INTO users (first_name, last_name, email, department, job_title) VALUES (?, ?, ?, ?, ?)',
                (first_name, last_name, email, department, job_title)
            )
            
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            
            self.logger.info(f"Added user {first_name} {last_name} with ID {user_id}")
            return user_id
        except sqlite3.IntegrityError:
            self.logger.warning(f"User with email {email} already exists")
            conn.close()
            return None
        except Exception as e:
            self.logger.error(f"Error adding user: {str(e)}")
            conn.close()
            raise
    
    def find_users_by_name(self, name):
        """
        Find users by name (can be first name, last name, or full name)
        Returns a list of tuples (first_name, last_name, email)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Split the name into parts
            name_parts = name.strip().split()
            
            if len(name_parts) == 1:
                # Single name part - search in both first and last name
                name_part = name_parts[0]
                query = '''
                SELECT first_name, last_name, email 
                FROM users 
                WHERE first_name LIKE ? OR last_name LIKE ?
                ORDER BY first_name, last_name
                '''
                cursor.execute(query, (f'%{name_part}%', f'%{name_part}%'))
            else:
                # Multiple name parts - assume first part is first name and last part is last name
                first_part = name_parts[0]
                last_part = name_parts[-1]
                
                query = '''
                SELECT first_name, last_name, email 
                FROM users 
                WHERE (first_name LIKE ? AND last_name LIKE ?)
                ORDER BY first_name, last_name
                '''
                cursor.execute(query, (f'%{first_part}%', f'%{last_part}%'))
            
            results = cursor.fetchall()
            conn.close()
            
            self.logger.info(f"Found {len(results)} users matching name '{name}'")
            return results
        except Exception as e:
            self.logger.error(f"Error finding users by name: {str(e)}")
            if 'conn' in locals():
                conn.close()
            raise
    
    def find_exact_user(self, first_name, last_name):
        """
        Find users with exact first and last name
        Returns a list of tuples (first_name, last_name, email)
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = '''
            SELECT first_name, last_name, email 
            FROM users 
            WHERE first_name = ? AND last_name = ?
            ORDER BY first_name, last_name
            '''
            cursor.execute(query, (first_name, last_name))
            
            results = cursor.fetchall()
            conn.close()
            
            self.logger.info(f"Found {len(results)} users with exact name '{first_name} {last_name}'")
            return results
        except Exception as e:
            self.logger.error(f"Error finding users by exact name: {str(e)}")
            if 'conn' in locals():
                conn.close()
            raise
    
    def get_all_users(self):
        """Get all users from the database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT first_name, last_name, email FROM users ORDER BY first_name, last_name')
            results = cursor.fetchall()
            conn.close()
            
            return results
        except Exception as e:
            self.logger.error(f"Error getting all users: {str(e)}")
            if 'conn' in locals():
                conn.close()
            raise
    
    def import_users_from_csv(self, csv_path):
        """Import users from a CSV file"""
        import csv
        
        try:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                added_count = 0
                error_count = 0
                
                for row in reader:
                    try:
                        first_name = row.get('first_name') or row.get('firstName') or ''
                        last_name = row.get('last_name') or row.get('lastName') or ''
                        email = row.get('email') or ''
                        department = row.get('department') or None
                        job_title = row.get('job_title') or row.get('title') or None
                        
                        if not (first_name and last_name and email):
                            raise ValueError("Missing required fields")
                        
                        cursor.execute(
                            'INSERT INTO users (first_name, last_name, email, department, job_title) VALUES (?, ?, ?, ?, ?)',
                            (first_name, last_name, email, department, job_title)
                        )
                        added_count += 1
                    except Exception as e:
                        self.logger.warning(f"Error importing user {row}: {str(e)}")
                        error_count += 1
                
                conn.commit()
                conn.close()
                
                self.logger.info(f"Imported {added_count} users, {error_count} errors")
                return added_count, error_count
        except Exception as e:
            self.logger.error(f"Error importing users from CSV: {str(e)}")
            if 'conn' in locals():
                conn.close()
            raise