
import os

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash
)

from db import get_db_connection
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("SECRET_KEY is missing from environment variables.")


# ==========================================
# DASHBOARD
# ==========================================

@app.route("/")
def home():

    connection = get_db_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                (SELECT COUNT(*) FROM book_copies),
                (SELECT COUNT(*) FROM students),
                (SELECT COUNT(*) FROM issue_records
                 WHERE status = 'Issued'),
                (SELECT COUNT(*) FROM book_copies
                 WHERE status = 'Available')
        """)

        stats = cursor.fetchone()

        cursor.execute("""
            SELECT
                b.book_id,
                b.title,
                COALESCE(a.author_name, 'Unknown'),
                COALESCE(c.category_name, 'Uncategorized'),
                CASE
                    WHEN COUNT(bc.copy_id) FILTER
                        (WHERE bc.status = 'Available') > 0
                    THEN 'Available'
                    WHEN COUNT(bc.copy_id) > 0
                    THEN 'Issued'
                    ELSE 'No Copies'
                END
            FROM books b
            LEFT JOIN authors a
                ON b.author_id = a.author_id
            LEFT JOIN categories c
                ON b.category_id = c.category_id
            LEFT JOIN book_copies bc
                ON b.book_id = bc.book_id
            GROUP BY b.book_id, a.author_name,
                     c.category_name, b.created_at
            ORDER BY b.created_at DESC
            LIMIT 5
        """)

        recent_books = cursor.fetchall()
        cursor.close()

        return render_template(
            "index.html",
            total_books=stats[0],
            total_students=stats[1],
            books_issued=stats[2],
            available_books=stats[3],
            recent_books=recent_books
        )

    finally:
        connection.close()


# ==========================================
# VIEW AND SEARCH BOOKS
# ==========================================

@app.route("/books")
def books():

    search = request.args.get("search", "").strip()

    connection = get_db_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                b.book_id,
                b.title,
                b.isbn,
                a.author_name,
                c.category_name,
                COUNT(bc.copy_id),
                COUNT(bc.copy_id) FILTER
                    (WHERE bc.status = 'Available')
            FROM books b
            LEFT JOIN authors a
                ON b.author_id = a.author_id
            LEFT JOIN categories c
                ON b.category_id = c.category_id
            LEFT JOIN book_copies bc
                ON b.book_id = bc.book_id
            WHERE
                b.title ILIKE %s
                OR b.isbn ILIKE %s
                OR COALESCE(a.author_name, '') ILIKE %s
                OR COALESCE(c.category_name, '') ILIKE %s
            GROUP BY b.book_id, a.author_name,
                     c.category_name
            ORDER BY b.book_id DESC
        """, (
            f"%{search}%",
            f"%{search}%",
            f"%{search}%",
            f"%{search}%"
        ))

        book_list = cursor.fetchall()
        cursor.close()

        return render_template(
            "books.html",
            books=book_list,
            search=search,
            book_count=len(book_list)
        )

    finally:
        connection.close()


# ==========================================
# ADD NEW BOOK
# ==========================================

@app.route("/books/add", methods=["GET", "POST"])
def add_book():

    connection = get_db_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT author_id, author_name
            FROM authors ORDER BY author_name
        """)
        authors = cursor.fetchall()

        cursor.execute("""
            SELECT category_id, category_name
            FROM categories ORDER BY category_name
        """)
        categories = cursor.fetchall()

        if request.method == "POST":

            title = request.form.get("title", "").strip()
            isbn = request.form.get("isbn", "").strip()
            publisher = request.form.get("publisher", "").strip()

            try:
                author_id = int(request.form.get("author_id", ""))
                category_id = int(request.form.get("category_id", ""))
                copies = int(request.form.get("copies", "1"))

                year_text = request.form.get(
                    "publication_year", ""
                ).strip()

                publication_year = (
                    int(year_text) if year_text else None
                )

                if not title or not isbn:
                    raise ValueError("Title and ISBN are required.")

                if copies < 1 or copies > 1000:
                    raise ValueError("Copies must be between 1 and 1000.")

                if publication_year is not None and not (
                    1 <= publication_year <= 2100
                ):
                    raise ValueError("Enter a valid publication year.")

            except ValueError as error:
                connection.rollback()
                flash(str(error), "danger")

                return render_template(
                    "add_book.html",
                    authors=authors,
                    categories=categories
                )

            try:
                cursor.execute("""
                    INSERT INTO books
                    (title, isbn, author_id, category_id,
                     publisher, publication_year)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING book_id
                """, (
                    title, isbn, author_id, category_id,
                    publisher or None, publication_year
                ))

                book_id = cursor.fetchone()[0]

                cursor.executemany("""
                    INSERT INTO book_copies (book_id, status)
                    VALUES (%s, 'Available')
                """, [(book_id,) for _ in range(copies)])

                connection.commit()

                flash("Book added successfully!", "success")
                return redirect(url_for("books"))

            except Exception as error:
                connection.rollback()
                flash(
                    "Could not add book. Check whether the ISBN "
                    "already exists and verify the details.",
                    "danger"
                )
                print("Add book error:", error)

        cursor.close()

        return render_template(
            "add_book.html",
            authors=authors,
            categories=categories
        )

    finally:
        connection.close()


# ==========================================
# EDIT BOOK
# ==========================================

@app.route("/books/edit/<int:book_id>", methods=["GET", "POST"])
def edit_book(book_id):

    connection = get_db_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT book_id, title, isbn, author_id,
                   category_id, publisher, publication_year
            FROM books
            WHERE book_id = %s
        """, (book_id,))

        book = cursor.fetchone()

        if not book:
            flash("Book not found.", "danger")
            return redirect(url_for("books"))

        cursor.execute("""
            SELECT author_id, author_name
            FROM authors ORDER BY author_name
        """)
        authors = cursor.fetchall()

        cursor.execute("""
            SELECT category_id, category_name
            FROM categories ORDER BY category_name
        """)
        categories = cursor.fetchall()

        if request.method == "POST":

            title = request.form.get("title", "").strip()
            isbn = request.form.get("isbn", "").strip()
            publisher = request.form.get("publisher", "").strip()

            try:
                author_id = int(request.form.get("author_id", ""))
                category_id = int(request.form.get("category_id", ""))

                year_text = request.form.get(
                    "publication_year", ""
                ).strip()

                publication_year = (
                    int(year_text) if year_text else None
                )

                if not title or not isbn:
                    raise ValueError("Title and ISBN are required.")

                if publication_year is not None and not (
                    1 <= publication_year <= 2100
                ):
                    raise ValueError("Enter a valid publication year.")

            except ValueError as error:
                flash(str(error), "danger")
                return render_template(
                    "edit_book.html",
                    book=book,
                    authors=authors,
                    categories=categories
                )

            try:
                cursor.execute("""
                    UPDATE books
                    SET title = %s,
                        isbn = %s,
                        author_id = %s,
                        category_id = %s,
                        publisher = %s,
                        publication_year = %s
                    WHERE book_id = %s
                """, (
                    title, isbn, author_id, category_id,
                    publisher or None, publication_year, book_id
                ))

                connection.commit()

                flash("Book updated successfully!", "success")
                return redirect(url_for("books"))

            except Exception as error:
                connection.rollback()
                flash(
                    "Could not update book. Check whether the ISBN "
                    "already exists.",
                    "danger"
                )
                print("Edit book error:", error)

        cursor.close()

        return render_template(
            "edit_book.html",
            book=book,
            authors=authors,
            categories=categories
        )

    finally:
        connection.close()


# ==========================================
# DELETE BOOK
# ==========================================

@app.route("/books/delete/<int:book_id>", methods=["POST"])
def delete_book(book_id):

    connection = get_db_connection()

    try:
        cursor = connection.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM issue_records ir
            JOIN book_copies bc ON ir.copy_id = bc.copy_id
            WHERE bc.book_id = %s
        """, (book_id,))

        issue_history = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*)
            FROM reservations
            WHERE book_id = %s
        """, (book_id,))

        reservation_count = cursor.fetchone()[0]

        if issue_history > 0 or reservation_count > 0:
            flash(
                "Cannot delete this book because it has borrowing "
                "history or reservations.",
                "warning"
            )

            return redirect(url_for("books"))

        cursor.execute("""
            DELETE FROM book_copies
            WHERE book_id = %s
        """, (book_id,))

        cursor.execute("""
            DELETE FROM books
            WHERE book_id = %s
        """, (book_id,))

        if cursor.rowcount == 0:
            connection.rollback()
            flash("Book not found.", "danger")
        else:
            connection.commit()
            flash("Book deleted successfully!", "success")

        cursor.close()

    except Exception as error:
        connection.rollback()
        flash("Unable to delete this book.", "danger")
        print("Delete book error:", error)

    finally:
        connection.close()

    return redirect(url_for("books"))


if __name__ == "__main__":
    app.run(debug=True)
