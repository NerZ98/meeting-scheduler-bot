import argparse
import csv
import os
import sys
from user_database import UserDatabase

def add_test_users(db_path):
    """Add sample test users to the database"""
    db = UserDatabase(db_path)

    test_users = [
        ('Love', 'Verma', 'love.verma1@biz4solutions.com', 'Engineering', 'Software Engineer'),
    ]

    added_count = 0
    error_count = 0

    for first_name, last_name, email, department, job_title in test_users:
        try:
            user_id = db.add_user(first_name, last_name, email, department, job_title)
            if user_id:
                added_count += 1
            else:
                error_count += 1
        except Exception as e:
            print(f"Error adding user {first_name} {last_name}: {str(e)}")
            error_count += 1

    print(f"Successfully added {added_count} test users.")
    if error_count > 0:
        print(f"Encountered {error_count} errors.")

    return True

def main():
    parser = argparse.ArgumentParser(description='Populate the user database')
    parser.add_argument('--db', type=str, default='users.db', help='Path to the database file')
    args = parser.parse_args()
    add_test_users(args.db)

if __name__ == "__main__":
    main()
