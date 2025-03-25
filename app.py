import os
import csv
import zipfile
import psycopg2
import pandas as pd
from flask import Flask, render_template, request, session, make_response, redirect, url_for, make_response, flash, jsonify, send_file, Response, abort
from weasyprint import HTML
import re
from urllib.parse import unquote
import fitz  # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from io import BytesIO, StringIO
import io
from num2words import num2words
from datetime import datetime, date
from werkzeug.security import check_password_hash
from psycopg2.extras import DictCursor

# PostgreSQL Database Configuration
DB_PARAMS = {
    "dbname": os.environ.get("DB_NAME", "rmc_sales_n53i"),
    "user": os.environ.get("DB_USER", "angadr"),
    "password": os.environ.get("DB_PASSWORD", "J8hmHOaf84rCOCz7n3MvLjPTTUjp81Ps"),
    "host": os.environ.get("DB_HOST", "dpg-cv9hi28fnakc739q7h50-a.singapore-postgres.render.com"),
    "port": os.environ.get("DB_PORT", "5432"),
    "sslmode": "require"  # Required for external connections
}

app = Flask(__name__)
app.secret_key = os.urandom(24)


# MISC Functions used

# Function to convert YYYY-MM-DD to DD/MM/YYYY

def format_date(date_str):
    if isinstance(date_str, (datetime, date)):  # If it's already a date or datetime object
        return date_str.strftime("%d.%m.%Y")
    elif isinstance(date_str, str):  # If it's a string in YYYY-MM-DD format
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    return ""  # Return empty string for None or unexpected values


# Function used to convert into indian currency format (1,00,000.00)
def format_indian_currency(num):
    num = float(num)  # Ensure the input is a float
    # Convert number to Indian format (e.g., 1,23,456.78)
    integer, decimal = f"{num:,.2f}".split('.')
    
    # Split the integer part and handle the Indian grouping
    integer = integer.replace(",", "")
    if len(integer) > 3:
        last_three = integer[-3:]
        other_numbers = integer[:-3]
        # Apply the Indian numbering format
        other_numbers = ','.join([other_numbers[max(i - 2, 0):i] for i in range(len(other_numbers), 0, -2)][::-1])
        formatted_integer = f"{other_numbers},{last_three}"
    else:
        formatted_integer = integer

    return f"{formatted_integer}.{decimal}"

# Function to extract state name from the buyer address
def extract_state_from_address(address):
    # List of Indian states
    indian_states = [
        'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh', 'Goa', 'Gujarat',
        'Haryana', 'Himachal Pradesh', 'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra',
        'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland', 'Odisha', 'Punjab', 'Rajasthan', 'Sikkim', 'Tamil Nadu',
        'Telangana', 'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal', 'Andaman and Nicobar Islands',
        'Chandigarh', 'Dadra and Nagar Haveli and Daman and Diu', 'Delhi', 'Jammu and Kashmir', 'Ladakh', 
        'Lakshadweep', 'Puducherry'
    ]

    # Iterate through the states and check if any state is in the address
    for state in indian_states:
        # Use a case-insensitive match
        if re.search(rf"\b{state}\b", address, re.IGNORECASE):
            return state

    return None

# Invoice replacing "/" with "-" in the middle
def replace_slash_with_hyphen(invoice_id):
    # Split the string by '/'
    parts = invoice_id.split('/')
    return (parts[0]+"/"+parts[1]+"-"+parts[2]+"/"+parts[3])

# Function to connect to the database
def get_db_connection():
    return psycopg2.connect(**DB_PARAMS)

# Function to convert amount in numbers to words
def convert_amount_to_words(amount):
    # Convert the numeric amount to words and append "only" at the end
    amount_in_words = num2words(amount, lang='en_IN').capitalize() + " only."
    return amount_in_words

# Function to wrap text within box boundaries without cutting off words
def draw_wrapped_text(canvas, x, y, text, box_width, default_box_height, max_box_height, max_font_size=12):
    font_size = max_font_size
    box_height = default_box_height
    
    # Normalize line breaks and preserve blank lines
    text = text.replace("\r\n", "\n")
    paragraphs = text.splitlines()

    while font_size > 6:
        text_object = canvas.beginText(x + 2, y - 2)
        text_object.setFont("Helvetica", font_size)
        
        line_height = font_size + 1
        current_height = y
        lines = []

        # Process each paragraph, including blank lines for extra spacing
        for paragraph in paragraphs:
            if not paragraph.strip():  # Detect blank line for extra spacing
                lines.append("")  # Append a blank line
                continue
            
            words = paragraph.split()
            line = ""
            for word in words:
                if canvas.stringWidth(line + " " + word, "Helvetica", font_size) <= box_width:
                    line += " " + word if line else word
                else:
                    lines.append(line)
                    line = word
            if line:
                lines.append(line)

        # Calculate the required height for all lines
        required_height = len(lines) * line_height
        if required_height <= box_height:
            for line in lines:
                if line:  # Draw non-empty lines
                    text_object.setTextOrigin(x + 2, current_height - line_height)
                    text_object.textLine(line)
                current_height -= line_height
            canvas.drawText(text_object)
            canvas.rect(x, y - box_height, box_width, box_height, stroke=0, fill=0)
            return box_height
        else:
            if box_height < max_box_height:
                box_height = min(box_height + 5, max_box_height)
            else:
                font_size -= 0.5

    return box_height

def draw_centered_text(canvas, x, y, text, box_width, box_height, max_font_size=12):
    font_size = max_font_size
    while font_size > 6:
        canvas.setFont("Helvetica", font_size)
        text_width = canvas.stringWidth(text, "Helvetica", font_size)
        
        # Adjusted text height estimation (75% of font size typically gives better centering)
        text_height = font_size * 0.75

        # Check if the text width fits within the box
        if text_width <= box_width:
            # Calculate x and y to center the text within the box
            text_x = x + (box_width - text_width) / 2
            text_y = y - box_height / 2 - text_height / 4  # Fine-tuning vertical alignment

            # Draw the text without a border
            canvas.drawString(text_x, text_y, text)
            # Draw the text box without a border
            canvas.rect(x, y - box_height, box_width, box_height, stroke=0, fill=0)
            return
        else:
            font_size -= 0.5

def pdf_generate_new(invoice_data):
    # Step 1: Create an overlay PDF with the invoice data
    overlay_pdf_stream = BytesIO()
    c = canvas.Canvas(overlay_pdf_stream, pagesize=A4)
    
    # List of tick mark positions for each page (replace with desired coordinates for each page)
    tick_positions = [(408, 822), (408, 806), (408, 791)]  # Example coordinates

    for position in tick_positions:
        # Draw tick mark at specified position for this page
        c.drawString(position[0], position[1], "✓")
        
        # Draw other fixed details on each page
        draw_wrapped_text(c, 310, 765, invoice_data["invoice_no"], box_width=120, default_box_height=20, max_box_height=20)
        draw_wrapped_text(c, 310, 750, invoice_data["invoice_date"], box_width=100, default_box_height=20, max_box_height=20)
        if invoice_data["po_no_date"]!=None:
            draw_wrapped_text(c, 475, 765, invoice_data["po_no_date"], box_width=100, default_box_height=35, max_box_height=35)
        if invoice_data["dispatched_by"]!=None:
            draw_wrapped_text(c, 360, 705, invoice_data["dispatched_by"], box_width=150, default_box_height=30, max_box_height=30)
        draw_wrapped_text(c, 35, 655, invoice_data["buyer_details"], box_width=250, default_box_height=58, max_box_height=58)
        draw_wrapped_text(c, 305, 655, invoice_data["consignee_details"], box_width=265, default_box_height=58, max_box_height=58)

        # Calculate max height for description textbox based on number of items
        total_column_height = 270  # Set this according to available space
        num_items = len(invoice_data["goods"])
        max_description_height = total_column_height * (0.9 if num_items == 1 else 0.45) if num_items <= 2 else total_column_height / num_items
        default_description_height = 40

        # Loop through each item in the goods list
        y_position = 560
        for i, item in enumerate(invoice_data["goods"], start=1):
            draw_centered_text(c, 17, y_position, str(i), box_width=40, box_height=20)
            
            # Dynamically calculate the height needed for each description and adjust y_position for the next item
            description_height = draw_wrapped_text(
                c, 60, y_position, item["description"],
                box_width=197, default_box_height=default_description_height,
                max_box_height=max_description_height
            )
            
            draw_centered_text(c, 265, y_position, item["qty"], box_width=30, box_height=20)
            draw_centered_text(c, 300, y_position, item["hsn"], box_width=60, box_height=20)
            draw_centered_text(c, 365, y_position, item["rate"], box_width=105, box_height=20)
            draw_centered_text(c, 475, y_position, item["amount"], box_width=105, box_height=20)
            
            # Update y_position for the next row based on the current item's description box height
            y_position -= description_height + 10  # Adjust spacing between items if needed

        # Draw totals and other fields
        draw_centered_text(c, 475, 304, invoice_data["total_amount"], box_width=105, box_height=20)
        if invoice_data["buyer_state"] != "west bengal":
            draw_centered_text(c, 421, 233, invoice_data["igst"], box_width=25, box_height=20)
            draw_centered_text(c, 475, 233, invoice_data["igst_amount"], box_width=105, box_height=20)
        else:
            draw_centered_text(c, 423, 278, invoice_data["sgst"], box_width=25, box_height=20)
            draw_centered_text(c, 477, 278, invoice_data["sgst_amount"], box_width=105, box_height=20)
            draw_centered_text(c, 423, 258, invoice_data["cgst"], box_width=25, box_height=20)
            draw_centered_text(c, 477, 258, invoice_data["cgst_amount"], box_width=105, box_height=20)
        draw_centered_text(c, 475, 193, invoice_data["grand_total"], box_width=105, box_height=20)
        draw_wrapped_text(c, 40, 193, invoice_data["amount_in_words"], box_width=300, default_box_height=38, max_box_height=38)

        # Finalize and add this page
        c.showPage()
        
    c.save()
    overlay_pdf_stream.seek(0)
    template_path = "data/Tax Invoice 2024 TEMPLATE.pdf"
    template_pdf = fitz.open(template_path)
    overlay_pdf = fitz.open("pdf", overlay_pdf_stream)
    
    # Create a new PDF for output
    new_pdf = fitz.open()
    
    # Loop to merge each page with the template and overlay
    for page_index in range(len(tick_positions)):
        template_page = template_pdf[0]  # Base template page
        new_page = new_pdf.new_page(-1, width=template_page.rect.width, height=template_page.rect.height)
        
        # Show template content first
        new_page.show_pdf_page(new_page.rect, template_pdf, 0)
        
        # Apply overlay content
        new_page.show_pdf_page(new_page.rect, overlay_pdf, page_index)
    
    # Save PDF to a BytesIO object instead of a file
    pdf_data = BytesIO()
    new_pdf.save(pdf_data)
    pdf_data.seek(0)
    
    # Close PDFs
    template_pdf.close()
    overlay_pdf.close()
    new_pdf.close()

    # Return the binary data directly from the BytesIO object
    return pdf_data.getvalue()


# PAGE ROUTINGS

# Authentication and Roles
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        # Fetch the user by username only, no password in the SQL query
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT username, password, name, role FROM users WHERE username = %s', (username,))
                user = cur.fetchone()
        finally:
            conn.close()
            
        # Check if user exists and verify the password hash
        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['role'] = user[3]
            session['user_name'] = user[2]
            return redirect(url_for('home_page_new'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

# Function to logout
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.')
    return redirect(url_for('login'))

# Role-based access control
def role_required(role):
    def decorator(func):
        def wrapper(*args, **kwargs):
            if 'role' not in session or session['role'] != role:
                return "Access Denied", 403
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator

# Base page routing for login
@app.route('/')
def login_redirect():
    return redirect(url_for('login'))

# Home page routing
@app.route('/home')
def home_page_new():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session.get("user_id")
    user_name = session.get("user_name")
    user_role = session.get("role")
    return render_template('home_page_new.html', user_id=user_id, user_role=user_role, user_name=user_name)

# View invoices page routing
@app.route('/view_invoices_new')
def view_invoices_new():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()  # Create a cursor
    
    # Fetch all invoices
    cur.execute('SELECT * FROM invoices')
    invoices = cur.fetchall()
    
    # Fetch all invoice items
    cur.execute('SELECT * FROM invoice_items')
    invoice_items = cur.fetchall()

    # Create a dictionary to hold the structured invoice data
    invoice_data = []

    # Group invoice items by invoice_id
    items_by_invoice = {}
    for item in invoice_items:
        invoice_id = item[1]  # PostgreSQL returns tuples, so use indexing
        if invoice_id not in items_by_invoice:
            items_by_invoice[invoice_id] = []
        items_by_invoice[invoice_id].append({
            'itemID': item[0],  
            'description': item[2],  
            'hsnCode': item[3],  
            'quantity': item[4],  
            'rate': item[5],  
            'price': item[6]  
        })
    
    # Organize invoices and fetch associated buyer and consignee details
    for invoice in invoices:
        invoice_id = invoice[0]  # PostgreSQL returns tuples, so use indexing
        buyer_id = invoice[2]  
        address_id = invoice[3]  
        consignee_id = invoice[4]  # Fetch consignee_id from the invoice

        # Fetch buyer details
        cur.execute('SELECT buyer_name, buyer_gst FROM buyer_info WHERE buyer_id = %s', (buyer_id,))
        buyer = cur.fetchone()
        buyer_name = buyer[0] if buyer else "Unknown"
        buyer_gst = buyer[1] if buyer else "N/A"

        # Fetch buyer address
        cur.execute('SELECT address FROM buyer_addresses WHERE address_id = %s', (address_id,))
        buyer_address = cur.fetchone()
        buyer_address = buyer_address[0] if buyer_address else "No Address"

        # Fetch consignee address
        cur.execute('SELECT consignee_address FROM consignee_addresses WHERE consignee_id = %s', (consignee_id,))
        consignee_address = cur.fetchone()
        consignee_address = consignee_address[0] if consignee_address else "No Consignee Address"

        invoice_data.append({
            'invoiceID': invoice_id,
            'buyerName': buyer_name,
            'invoiceDate': format_date(invoice[1]),  # Format date properly
            'poDetails': invoice[5],  # Updated index for po_details
            'buyerAddress': buyer_address,
            'gstin': buyer_gst,
            'consignee': consignee_address,  # Use consignee address from the table
            'dispatch': invoice[6],  # Updated index for dispatch
            'totalPrice': invoice[7],  # Updated index for total_price
            'finalAmount': invoice[8],  # Updated index for final_amount
            'items': items_by_invoice.get(invoice_id, [])  
        })

    cur.close()
    conn.close()

    # Passing the structured data to the template
    return render_template(
        'view_invoices_new.html', 
        invoice_data=invoice_data, 
        format_indian_currency=format_indian_currency, 
        user_role=session.get("role")
    )


@app.route('/first_page_new')
@role_required('admin')
def first_page_new():
    # Get buyer_id, address_id, and consignee_id from request arguments
    buyer_id = request.args.get('buyer_id')
    address_id = request.args.get('address_id')
    consignee_id = request.args.get('consignee_id')
    buyer_info = None
    selected_address = None
    buyer_addresses = []
    consignee_addresses = []
    selected_consignee_address = None

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)

    if buyer_id:
        # Fetch buyer name and GST details from the database
        cursor.execute("SELECT buyer_name, buyer_gst FROM buyer_info WHERE buyer_id = %s", (buyer_id,))
        result = cursor.fetchone()
        if result:
            buyer_info = {
                'buyer_name': result['buyer_name'],
                'buyer_gst': result['buyer_gst']
            }

        # Retrieve all associated addresses for the buyer
        cursor.execute("SELECT address_id, address FROM buyer_addresses WHERE buyer_id = %s", (buyer_id,))
        buyer_addresses = [{'address_id': row['address_id'], 'address': row['address']} for row in cursor.fetchall()]

        # Set the selected address if address_id is provided
        if address_id:
            cursor.execute("SELECT address FROM buyer_addresses WHERE address_id = %s", (address_id,))
            selected_address_result = cursor.fetchone()
            selected_address = selected_address_result['address'] if selected_address_result else None

        # Retrieve all associated consignee addresses for the buyer
        cursor.execute("""
            SELECT ca.consignee_id, ca.consignee_address 
            FROM consignee_addresses ca
            JOIN buyer_addresses ba ON ca.buyer_id = ba.buyer_id
            WHERE ba.address_id = %s
        """, (address_id,))
        consignee_addresses = [{'consignee_id': row['consignee_id'], 'consignee_address': row['consignee_address']} for row in cursor.fetchall()]

        # Set the selected consignee address if consignee_id is provided
        if consignee_id:
            cursor.execute("SELECT consignee_address FROM consignee_addresses WHERE consignee_id = %s", (consignee_id,))
            selected_consignee_result = cursor.fetchone()
            selected_consignee_address = selected_consignee_result['consignee_address'] if selected_consignee_result else None
        elif len(consignee_addresses) == 1:
            # If only one consignee address exists and no specific ID is provided
            selected_consignee_address = consignee_addresses[0]['consignee_address']

    # Fetch the maximum invoice_id from the invoices table
    cursor.execute("SELECT MAX(invoice_id) FROM invoices")
    last_invoice_id = cursor.fetchone()[0]

    # Extract the numeric part of the invoice_id and increment it
    if last_invoice_id:
        # Assuming invoice_id follows the format "INV001", "INV002", etc.
        last_invoice_number = int(last_invoice_id[16:])  # Extract the numeric part after "INV"
        next_invoice_number = last_invoice_number + 1
    else:
        # If no invoices exist, start from 1
        next_invoice_number = 1

    # Format the next invoice number as a 3-digit string
    next_invoice_number = f"{next_invoice_number:03}"

    # Close the cursor and connection
    cursor.close()
    conn.close()

    # Render the template, passing buyer info, selected address, all addresses, consignee addresses, selected consignee address, and next invoice number
    return render_template(
        'first_page_new.html',
        buyer_info=buyer_info,
        selected_address=selected_address,
        buyer_addresses=buyer_addresses,
        consignee_addresses=consignee_addresses,
        selected_consignee_address=selected_consignee_address,
        next_invoice_number=next_invoice_number
    )

# Second page (form input) routing

@app.route('/second_page_new', methods=['GET', 'POST'])
@role_required('admin')
def second_page_new():
    # Storing form data in session variables
    year = request.form["year"]
    inv_id = request.form["inv_no"]
    session["Invoice_ID"] = f"RMC / {year} / {inv_id}"
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)  # Use DictCursor for easy access

    try:
        # Check if invoice ID already exists
        cur.execute('SELECT * FROM invoices WHERE invoice_id = %s', (session["Invoice_ID"],))  
        existing_invoice = cur.fetchone()  
        
        if existing_invoice:
            flash('Invoice number already exists. Please enter a unique invoice number.', 'error')
            return redirect(url_for('first_page_new'))
    
    except psycopg2.Error as e:
        conn.rollback()  # Rollback in case of an error
        flash('Database error: ' + str(e), 'error')
        return redirect(url_for('first_page_new'))
    
    finally:
        cur.close()  # Close cursor
        conn.close()  # Close connection

    # Store other form inputs in session
    session["Date"] = request.form["date"]
    session["PO_Details"] = request.form["po"] if request.form["po"] else None
    session["Dispatch"] = request.form["d_by"] if request.form["d_by"] else None
    session["Buyer_Name"] = request.form["b_name"]
    session["Buyer_Address"] = request.form["b_address"]
    session["Buyer_GST"] = request.form["b_gst"]
    session["Consignee"] = request.form["c_details"]

    # Extract buyer state from address
    buyer_address = session["Buyer_Address"]
    buyer_state = extract_state_from_address(buyer_address)
    session["Buyer_State"] = buyer_state

    if not buyer_state:
        flash('Please include a valid Indian state in the buyer address.', 'error')
        return redirect(url_for('first_page_new'))

    # Fetch consignee_id if consignee address is selected
    if "consigneeDropdown" in request.form:
        consignee_id = request.form["consigneeDropdown"]
        session["Consignee_ID"] = consignee_id
    else:
        session["Consignee_ID"] = None

    return render_template('second_page_new.html')

# Edit first invoice page routing
@app.route('/edit_first_invoice_new', methods=['GET'])
@role_required('admin')
def edit_first_invoice_new():
    # Redirect to the first page but the form will be pre-populated with session data
    return render_template('first_page_new.html')

# Third page (form input) routing
@app.route('/third_page_new', methods=['POST'])
@role_required('admin')
def third_page_new():
    try:
        no_of_items = int(request.form["n_items"])
        items = []
        total_price = 0

        # Process each item entered in the form
        for i in range(1, no_of_items + 1):
            try:
                qty = int(request.form[f'qty{i}'])
                rate = float(request.form[f'rate{i}'])  # Use float for precise calculations
                price = qty * rate

                item = {
                    'description': request.form[f'description{i}'],
                    'hsnCode': request.form[f'hsnCode{i}'],
                    'qty': qty,
                    'rate': rate,
                    'price': price,
                }

                items.append(item)
                total_price += price  # Accumulate total price

            except ValueError:
                flash(f"Invalid quantity or rate for item {i}. Please enter valid numbers.", "error")
                return redirect(url_for('second_page_new'))  # Redirect back to fix input errors

        # Store items and total price in session
        session["Items"] = items
        session["Total_Price"] = total_price

        # Initialize tax amounts
        igst = cgst = sgst = 0
        final_amount = total_price

        # Ensure buyer address exists in session
        if "Buyer_Address" in session:
            buyer_address = session["Buyer_Address"]
            buyer_state = extract_state_from_address(buyer_address)
            session["Buyer_State"] = buyer_state

            if buyer_state.lower() == 'west bengal':
                cgst = total_price * 0.09  # 9% CGST for within West Bengal
                sgst = total_price * 0.09  # 9% SGST for within West Bengal
                final_amount += cgst + sgst
            else:
                igst = total_price * 0.18  # 18% IGST for outside West Bengal
                final_amount += igst
        else:
            flash("Buyer address is missing. Please restart the process.", "error")
            return redirect(url_for('first_page_new'))

        # Store final calculated amount and tax details in session
        session.update({
            "final_amount": final_amount,
            "cgst": cgst,
            "sgst": sgst,
            "igst": igst,
        })

        # Render third_page_new.html with all the required data
        return render_template(
            'third_page_new.html',
            items=list(enumerate(items, start=1)),
            company_name="Riat Machinery Co.",
            buyer_name=session.get("Buyer_Name", "N/A"),
            invoice_date=format_date(session.get("Date", "N/A")),
            invoice_id=session.get("Invoice_ID", "N/A"),
            dispatch_details=session.get("Dispatch", "N/A"),
            cgst=cgst,
            sgst=sgst,
            igst=igst,
            buyer_address=buyer_address,
            buyer_gst=session.get("Buyer_GST", "N/A"),
            consignee=session.get("Consignee", "N/A"),
            final_amount=final_amount,
            total_price=total_price,
            po_details=session.get("PO_Details", "N/A"),
        )

    except ValueError:
        flash("Invalid input. Please check your data and try again.", "error")
        return redirect(url_for('second_page_new'))

    except Exception as e:
        flash(f"An unexpected error occurred: {str(e)}", "error")
        return redirect(url_for('second_page_new'))


# Submit invoice (form input) routing
@app.route('/submit_invoice_new', methods=['POST'])
@role_required('admin')
def submit_invoice_new():
    # Determine if the data is coming from the session (new invoice) or form (duplicate invoice)
    if "Buyer_Name" in session:
        # Data is coming from the session (new invoice)
        buyer_name = session["Buyer_Name"]
        buyer_address = session["Buyer_Address"]
        buyer_gst = session["Buyer_GST"]
        consignee_details = session["Consignee"]
        invoice_number = session["Invoice_ID"]
        invoice_date = session["Date"]
        po_details = session["PO_Details"]
        dispatch = session["Dispatch"]
        total_price = int(float(session["Total_Price"]))  # Convert to integer
        final_amount = int(float(total_price) * 1.18)  # Recalculate final_amount
        items = session["Items"]
    else:
        # Data is coming from the form (duplicate invoice)
        year = request.form.get("financial_year")
        buyer_name = request.form.get('buyer_name')
        buyer_address = request.form.get('buyer_address')
        buyer_gst = request.form.get('buyer_gst')
        consignee_details = request.form.get('consignee_details')
        inv_id = request.form.get('invoice_number')
        invoice_date = request.form.get('invoice_date')
        po_details = request.form.get('po_details')
        dispatch = request.form.get('dispatch')
        total_price = request.form.get('total_price')
        total_price = int(float(total_price))  # Convert to integer
        final_amount = int(float(total_price) * 1.18)  # Recalculate final_amount
        invoice_number = f"RMC / {year} / {inv_id}"
        buyer_state = extract_state_from_address(buyer_address)
        session["Buyer_State"] = buyer_state

        # Extract item details from the form
        items = []
        for key, value in request.form.items():
            if key.startswith('description_'):
                item_id = key.split('_')[1]
                description = value
                hsn_code = request.form.get(f'hsnCode_{item_id}')
                quantity = int(request.form.get(f'quantity_{item_id}'))  # Convert to integer
                rate = float(request.form.get(f'rate_{item_id}'))  # Convert to float
                price = int(float(request.form.get(f'price_{item_id}')))  # Convert to integer
                items.append({
                    'description': description,
                    'hsnCode': hsn_code,
                    'qty': quantity,
                    'rate': rate,
                    'price': price
                })

    # Validate that at least one item is present
    if not items:
        flash("At least one item is required to create an invoice.", "error")
        return redirect(request.referrer)

    # Save the new invoice to the database
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if the buyer exists in buyer_info and fetch the buyer_id if it does
    cursor.execute('SELECT buyer_id FROM buyer_info WHERE buyer_name = %s', (buyer_name,))
    result = cursor.fetchone()
    if result:
        # Existing buyer: fetch the buyer_id
        buyer_id = result[0]
        # Update buyer's GSTIN if needed
        cursor.execute('''
            UPDATE buyer_info 
            SET buyer_gst = %s 
            WHERE buyer_id = %s''',
            (buyer_gst, buyer_id))
    else:
        # New buyer: insert into buyer_info and fetch buyer_id
        cursor.execute('''INSERT INTO buyer_info (buyer_name, buyer_gst) VALUES (%s, %s) RETURNING buyer_id''',
                       (buyer_name, buyer_gst))
        buyer_id = cursor.fetchone()[0]

    # Check if buyer's address already exists in buyer_addresses and fetch address_id
    cursor.execute('SELECT address_id FROM buyer_addresses WHERE buyer_id = %s AND address = %s', (buyer_id, buyer_address))
    address_result = cursor.fetchone()
    if address_result:
        # Existing address: fetch the address_id
        address_id = address_result[0]
    else:
        # New address: insert into buyer_addresses and fetch address_id
        cursor.execute('''INSERT INTO buyer_addresses (buyer_id, address) VALUES (%s, %s) RETURNING address_id''',
                       (buyer_id, buyer_address))
        address_id = cursor.fetchone()[0]

    # Check if consignee address exists in consignee_addresses and fetch consignee_id
    cursor.execute('SELECT consignee_id FROM consignee_addresses WHERE buyer_id = %s AND consignee_address = %s', (buyer_id, consignee_details))
    consignee_result = cursor.fetchone()
    if consignee_result:
        # Existing consignee address: fetch the consignee_id
        consignee_id = consignee_result[0]
    else:
        # New consignee address: insert into consignee_addresses and fetch consignee_id
        cursor.execute('''INSERT INTO consignee_addresses (buyer_id, consignee_address) VALUES (%s, %s) RETURNING consignee_id''',
                       (buyer_id, consignee_details))
        consignee_id = cursor.fetchone()[0]

    # Insert invoice data into invoices table, linking to buyer_id, address_id, and consignee_id
    cursor.execute('''INSERT INTO invoices 
                      (invoice_id, invoice_date, buyer_id, address_id, consignee_id, po_details, dispatch,
                      total_price, final_amount) 
                      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                   (invoice_number, invoice_date, buyer_id, address_id, consignee_id, po_details,
                    dispatch, total_price, final_amount))

    # Insert each item into invoice_items table linked to this invoice
    for item in items:
        cursor.execute('''INSERT INTO invoice_items 
                          (invoice_id, description, hsn_code, quantity, rate, price) 
                          VALUES (%s, %s, %s, %s, %s, %s)''',
                       (invoice_number, item['description'], item['hsnCode'], item['qty'], item['rate'], item['price']))

    # Commit the transaction
    conn.commit()
    flash("Invoice saved successfully!", "success")

    # Close the cursor and connection
    cursor.close()
    conn.close()

    # Redirect to the invoice generation page
    return redirect(url_for('generate_invoice_new', invoice_id=invoice_number.replace('/', '-')))


# Generate pdf page routing
@app.route('/generate_invoice_new/<invoice_id>', methods=['GET'])
@role_required('admin')
def generate_invoice_new(invoice_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)  # DictCursor allows accessing columns by name
    
    try:
        # Decode the invoice_id
        decoded_invoice_id = invoice_id.replace('-', '/')
        invoice_id = replace_slash_with_hyphen(decoded_invoice_id)

        # Fetch invoice, item data, buyer, and address data
        cur.execute('SELECT * FROM invoices WHERE invoice_id = %s', (invoice_id,))
        invoice = cur.fetchone()

        cur.execute('SELECT * FROM invoice_items WHERE invoice_id = %s', (invoice_id,))
        items = cur.fetchall()
        if not invoice:
            return jsonify({"error": "Invoice not found"}), 404

        # Get buyer_id from the invoice
        cur.execute('SELECT * FROM buyer_info WHERE buyer_id = %s', (invoice["buyer_id"],))
        buyer_info = cur.fetchone()

        cur.execute('SELECT * FROM buyer_addresses WHERE address_id = %s', (invoice["address_id"],))
        buyer_address = cur.fetchone()

        # Get consignee address from consignee_addresses
        cur.execute('SELECT * FROM consignee_addresses WHERE consignee_id = %s', (invoice["consignee_id"],))
        consignee_address = cur.fetchone()

        if not buyer_info or not buyer_address or not consignee_address:
            return jsonify({"error": "Buyer or consignee details not found"}), 404

        # Calculate IGST/CGST/SGST and amount in words
        total_price = invoice["total_price"]
        amount_in_words = convert_amount_to_words(invoice["final_amount"])

        buyer_state = session.get("Buyer_State", "").lower()
        
        if buyer_state == "west bengal":
            cgst_amount = total_price * 0.09
            sgst_amount = total_price * 0.09

            invoice_data = {
                "invoice_no": invoice["invoice_id"],
                "invoice_date": format_date(invoice["invoice_date"]),
                "po_no_date": invoice["po_details"],
                "dispatched_by": invoice["dispatch"],
                "buyer_details": f"{buyer_info['buyer_name']}\n{buyer_address['address']}\nGSTIN {buyer_info['buyer_gst']}",
                "buyer_state": buyer_state,
                "consignee_details": consignee_address["consignee_address"],  # Use consignee address from the table
                "goods": [
                    {
                        "description": item["description"],
                        "qty": str(item["quantity"]),
                        "hsn": item["hsn_code"],
                        "rate": format_indian_currency(item["rate"]),
                        "amount": format_indian_currency(item["price"])
                    }
                    for item in items
                ],
                "cgst": "9",
                "sgst": "9",
                "cgst_amount": format_indian_currency(cgst_amount),
                "sgst_amount": format_indian_currency(sgst_amount),
                "total_amount": format_indian_currency(total_price),
                "grand_total": format_indian_currency(invoice["final_amount"]),
                "amount_in_words": amount_in_words
            }
        
        else:
            igst_amount = total_price * 0.18

            invoice_data = {
                "invoice_no": invoice["invoice_id"],
                "invoice_date": format_date(invoice["invoice_date"]),
                "po_no_date": invoice["po_details"],
                "dispatched_by": invoice["dispatch"],
                "buyer_details": f"{buyer_info['buyer_name']}\n{buyer_address['address']}\nGSTIN {buyer_info['buyer_gst']}",
                "buyer_state": buyer_state,
                "consignee_details": consignee_address["consignee_address"],  # Use consignee address from the table
                "goods": [
                    {
                        "description": item["description"],
                        "qty": str(item["quantity"]),
                        "hsn": item["hsn_code"],
                        "rate": format_indian_currency(item["rate"]),
                        "amount": format_indian_currency(item["price"])
                    }
                    for item in items
                ],
                "igst": "18",
                "igst_amount": format_indian_currency(igst_amount),
                "total_amount": format_indian_currency(total_price),
                "grand_total": format_indian_currency(invoice["final_amount"]),
                "amount_in_words": amount_in_words
            }

        # Generate PDF
        pdf_data = pdf_generate_new(invoice_data)

        # Store PDF as BYTEA in PostgreSQL
        cur.execute('UPDATE invoices SET pdf_invoice = %s WHERE invoice_id = %s', (psycopg2.Binary(pdf_data), invoice_id))
        conn.commit()

        # Retain user_id and role in session, clear other session data
        user_id = session.get("user_id")
        role = session.get("role")
        user_name = session.get("user_name")
        session.clear()
        session["user_id"] = user_id
        session["role"] = role
        session["user_name"] = user_name

        return render_template('invoice_submitted_new.html', invoice_no=invoice_data["invoice_no"])

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500

    finally:
        cur.close()
        conn.close()


@app.route('/edit_invoice_new/<invoice_id>', methods=['GET', 'POST'])
@role_required('admin')
def edit_invoice_new(invoice_id):
    # Decode the invoice_id from the URL
    decoded_invoice_id = invoice_id.replace('-', '/')
    decoded_invoice_id = replace_slash_with_hyphen(decoded_invoice_id)

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)

    # Fetch invoice, buyer, address, and consignee details
    cursor.execute('''
        SELECT invoices.*, buyer_info.buyer_name, buyer_addresses.address, buyer_info.buyer_gst, consignee_addresses.consignee_address
        FROM invoices
        JOIN buyer_info ON invoices.buyer_id = buyer_info.buyer_id
        JOIN buyer_addresses ON invoices.address_id = buyer_addresses.address_id
        LEFT JOIN consignee_addresses ON invoices.consignee_id = consignee_addresses.consignee_id
        WHERE invoices.invoice_id = %s
    ''', (decoded_invoice_id,))
    invoice = cursor.fetchone()

    cursor.execute('SELECT * FROM invoice_items WHERE invoice_id = %s', (decoded_invoice_id,))
    invoice_items = cursor.fetchall()

    if invoice is None:
        return "Invoice not found", 404

    if request.method == 'POST':
        # Fetch form data
        buyer_name = request.form['buyer_name']
        invoice_date = request.form['invoice_date']
        po_details = request.form.get('po_details', None)
        buyer_address = request.form['buyer_address']
        buyer_state = extract_state_from_address(buyer_address)
        session["Buyer_State"] = buyer_state
        buyer_gst = request.form['buyer_gst']
        consignee_address = request.form['consignee_details']  # Updated to match the form field
        dispatch = request.form.get('dispatch', None)
        total_price = float(request.form['total_price'])
        final_amount = float(request.form['final_amount'])

        # Update each invoice item
        for item in invoice_items:
            item_id = item['item_id']  # Using dictionary-based access
            description = request.form[f'description_{item_id}']
            hsn_code = request.form[f'hsnCode_{item_id}']
            qty = int(request.form[f'quantity_{item_id}'])
            rate = float(request.form[f'rate_{item_id}'])
            price = qty * rate

            cursor.execute('''
                UPDATE invoice_items 
                SET description = %s, hsn_code = %s, quantity = %s, rate = %s, price = %s 
                WHERE item_id = %s AND invoice_id = %s
            ''', (description, hsn_code, qty, rate, price, item_id, decoded_invoice_id))

        # Check if the new buyer exists
        cursor.execute('SELECT * FROM buyer_info WHERE buyer_name = %s', (buyer_name,))
        new_buyer = cursor.fetchone()

        if new_buyer:
            new_buyer_id = new_buyer['buyer_id']

            cursor.execute('SELECT * FROM buyer_addresses WHERE buyer_id = %s AND address = %s', (new_buyer_id, buyer_address))
            existing_address = cursor.fetchone()

            cursor.execute('''
                UPDATE buyer_info
                SET buyer_gst = %s
                WHERE buyer_id = %s
            ''', (buyer_gst, new_buyer_id))

            if not existing_address:
                cursor.execute('''
                    INSERT INTO buyer_addresses (buyer_id, address)
                    VALUES (%s, %s) RETURNING address_id
                ''', (new_buyer_id, buyer_address))
                address_id = cursor.fetchone()['address_id']
            else:
                address_id = existing_address['address_id']

        else:
            cursor.execute('''
                INSERT INTO buyer_info (buyer_name, buyer_gst)
                VALUES (%s, %s) RETURNING buyer_id
            ''', (buyer_name, buyer_gst))
            new_buyer_id = cursor.fetchone()['buyer_id']

            cursor.execute('''
                INSERT INTO buyer_addresses (buyer_id, address)
                VALUES (%s, %s) RETURNING address_id
            ''', (new_buyer_id, buyer_address))
            address_id = cursor.fetchone()['address_id']

        # Check if the consignee address exists
        cursor.execute('SELECT * FROM consignee_addresses WHERE buyer_id = %s AND consignee_address = %s', (new_buyer_id, consignee_address))
        existing_consignee = cursor.fetchone()

        if existing_consignee:
            consignee_id = existing_consignee['consignee_id']
        else:
            cursor.execute('''
                INSERT INTO consignee_addresses (buyer_id, consignee_address)
                VALUES (%s, %s) RETURNING consignee_id
            ''', (new_buyer_id, consignee_address))
            consignee_id = cursor.fetchone()['consignee_id']

        # Update the invoice
        cursor.execute('''
            UPDATE invoices 
            SET buyer_id = %s, address_id = %s, consignee_id = %s, invoice_date = %s, total_price = %s, final_amount = %s, 
                po_details = %s, dispatch = %s
            WHERE invoice_id = %s
        ''', (new_buyer_id, address_id, consignee_id, invoice_date, total_price, final_amount, po_details, dispatch, decoded_invoice_id))

        conn.commit()
        cursor.close()
        conn.close()

        return redirect(url_for('generate_invoice_new', invoice_id=invoice_id))

    conn.close()
    invoice_date_str = invoice['invoice_date'].strftime('%Y-%m-%d') if invoice['invoice_date'] else ''
    return render_template('edit_invoice_new.html', invoice=invoice, invoice_items=invoice_items, format_indian_currency=format_indian_currency, invoice_date_str=invoice_date_str)

@app.route('/view_pdf_new/<invoice_id>')
def view_pdf_new(invoice_id):
    # Replace '-' with '/' if invoice IDs are stored in the database with slashes
    invoice_id = invoice_id.replace('-', '/')
    invoice_id = replace_slash_with_hyphen(invoice_id)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch the PDF invoice from the database
        cursor.execute("SELECT pdf_invoice FROM invoices WHERE invoice_id = %s", (invoice_id,))
        result = cursor.fetchone()

        if result and result[0]:
            pdf_data = result[0]
            return Response(pdf_data, mimetype='application/pdf')
        else:
            return "PDF not found for this invoice.", 404

    except Exception as e:
        return f"Database error: {str(e)}", 500

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()
    

@app.route('/buyer_table_new')
def buyer_table_new():
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Fetch buyer information along with multiple addresses and consignee addresses
        cursor.execute('''
            SELECT buyer_info.buyer_id, buyer_info.buyer_name, buyer_info.buyer_gst, 
                   buyer_addresses.address, buyer_addresses.address_id,
                   consignee_addresses.consignee_address, consignee_addresses.consignee_id
            FROM buyer_info
            LEFT JOIN buyer_addresses ON buyer_info.buyer_id = buyer_addresses.buyer_id
            LEFT JOIN consignee_addresses ON buyer_info.buyer_id = consignee_addresses.buyer_id
            ORDER BY buyer_info.buyer_id
        ''')

        # Fetch all rows
        raw_data = cursor.fetchall()

    finally:
        conn.close()

    # Organize data by buyer_id to group addresses and consignee addresses
    buyers = {}
    for row in raw_data:
        buyer_id = row['buyer_id']
        buyer_name = row['buyer_name']
        buyer_gst = row['buyer_gst']
        address = row['address']
        address_id = row['address_id']
        consignee_address = row['consignee_address']
        consignee_id = row['consignee_id']

        if buyer_id not in buyers:
            buyers[buyer_id] = {
                'buyer_name': buyer_name,
                'buyer_gst': buyer_gst,
                'addresses': [],
                'address_id': [],
                'consignee_addresses': [],
                'consignee_id': []
            }
        if address:
            buyers[buyer_id]['addresses'].append(address)
            buyers[buyer_id]['address_id'].append(address_id)
        if consignee_address:
            buyers[buyer_id]['consignee_addresses'].append(consignee_address)
            buyers[buyer_id]['consignee_id'].append(consignee_id)

    # Pass the data to the template
    return render_template('buyer_table_new.html', buyers=buyers, user_role=session.get("role"))


@app.route('/delete_invoice_new/<invoice_id>', methods=['POST'])
@role_required('admin')
def delete_invoice_new(invoice_id):
    # Convert invoice_id to match the database format if necessary
    decoded_invoice_id = invoice_id.replace('-', '/')
    decoded_invoice_id = replace_slash_with_hyphen(decoded_invoice_id)

    conn = None

    try:
        # Connect to the PostgreSQL database
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()

        # Begin a transaction to ensure both deletions succeed or fail together
        cursor.execute('BEGIN')
        
        # Delete associated items from the invoice_items table
        cursor.execute('DELETE FROM invoice_items WHERE invoice_id = %s', (decoded_invoice_id,))
        
        # Delete the invoice from the invoices table
        cursor.execute('DELETE FROM invoices WHERE invoice_id = %s', (decoded_invoice_id,))
        
        # Commit the transaction if both deletions are successful
        conn.commit()

    except Exception as e:
        # Rollback in case of error
        if conn:
            conn.rollback()
        return f"Error deleting invoice: {e}", 500

    finally:
        # Ensure the connection is closed properly
        if conn:
            conn.close()

    # Redirect back to the view invoices page after successful deletion
    return redirect(url_for('view_invoices_new'))

@app.route('/delete_buyer_new/<buyer_id>', methods=['POST'])
@role_required('admin')
def delete_buyer_new(buyer_id):
    conn = None

    try:
        # Connect to the PostgreSQL database
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()

        # Begin a transaction to ensure all deletions succeed or fail together
        cursor.execute('BEGIN')
        
        # Delete associated invoices and invoice items for this buyer
        cursor.execute('DELETE FROM invoice_items WHERE invoice_id IN (SELECT invoice_id FROM invoices WHERE buyer_id = %s)', (buyer_id,))
        cursor.execute('DELETE FROM invoices WHERE buyer_id = %s', (buyer_id,))
        
        # Delete the addresses associated with this buyer
        cursor.execute('DELETE FROM buyer_addresses WHERE buyer_id = %s', (buyer_id,))
        
        # Delete the buyer from the buyer_info table
        cursor.execute('DELETE FROM buyer_info WHERE buyer_id = %s', (buyer_id,))
        
        # Commit the transaction if all deletions are successful
        conn.commit()

    except Exception as e:
        # Rollback the transaction in case of error
        if conn:
            conn.rollback()
        return f"Error deleting buyer: {e}", 500

    finally:
        # Ensure the connection is closed properly
        if conn:
            conn.close()

    # Redirect back to the buyer table page after successful deletion
    return redirect(url_for('buyer_table_new'))


@app.route('/check_buyer', methods=['POST'])
@role_required('admin')
def check_buyer():
    data = request.get_json()
    buyer_name = data.get('buyer_name', '').strip()

    conn = None
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()

        # Perform a case-insensitive search using ILIKE
        query = "SELECT buyer_id, buyer_name, buyer_gst FROM buyer_info WHERE buyer_name ILIKE %s"
        cursor.execute(query, (f"%{buyer_name}%",))
        results = cursor.fetchall()

        buyers = []
        if results:
            for buyer_id, buyer_name, buyer_gst in results:
                # Fetch all addresses for each buyer
                cursor.execute("SELECT address, address_id FROM buyer_addresses WHERE buyer_id = %s", (buyer_id,))
                addresses = cursor.fetchall()
                
                # Fetch all consignee addresses for each buyer
                cursor.execute("SELECT consignee_address, consignee_id FROM consignee_addresses WHERE buyer_id = %s", (buyer_id,))
                consignees = cursor.fetchall()

                # Convert addresses and consignees from tuples to lists of dictionaries
                address_list = [{'address': addr[0], 'address_id': addr[1]} for addr in addresses]
                consignee_list = [{'consignee_address': cons[0], 'consignee_id': cons[1]} for cons in consignees]

                buyers.append({
                    'buyer_id': buyer_id,
                    'buyer_name': buyer_name,
                    'buyer_gst': buyer_gst,
                    'addresses': address_list,
                    'consignees': consignee_list
                })
        return jsonify({'exists': bool(buyers), 'buyers': buyers})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        if conn:
            conn.close()
    

@app.route('/export_invoices_csv')
def export_invoices_csv():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch invoices data
    cursor.execute("""
        SELECT i.invoice_id, i.invoice_date, b.buyer_name, ba.address, ca.consignee_address, 
               b.buyer_gst, i.po_details, i.dispatch, i.total_price, i.final_amount
        FROM invoices i
        JOIN buyer_info b ON i.buyer_id = b.buyer_id
        JOIN buyer_addresses ba ON i.address_id = ba.address_id
        JOIN consignee_addresses ca ON i.consignee_id = ca.consignee_id
        ORDER BY i.invoice_id ASC
    """)
    invoices_data = cursor.fetchall()

    # Fetch invoice items data
    cursor.execute("""
        SELECT item_id, invoice_id, description, hsn_code, quantity, rate, price
        FROM invoice_items
        ORDER BY invoice_id ASC
    """)
    items_data = cursor.fetchall()

    conn.close()

    # Create in-memory ZIP file
    zip_buffer = BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        # Invoices CSV
        invoices_csv = StringIO()
        invoices_writer = csv.writer(invoices_csv, quoting=csv.QUOTE_MINIMAL, lineterminator='\n')

        # Write headers
        invoices_writer.writerow(["Invoice ID", "Invoice Date", "Buyer Name", "Buyer Address", "Consignee Address",
                                  "Buyer GST", "PO Details", "Dispatch Details", "Total Price", "Final Amount"])
        
        # Write data rows
        for row in invoices_data:
            invoice_id, invoice_date, buyer_name, buyer_address, consignee_address, buyer_gst, po_details, dispatch, total_price, final_amount = row
            formatted_date = invoice_date.strftime("%d/%m/%Y") if isinstance(invoice_date, (datetime, date)) else invoice_date

            invoices_writer.writerow([invoice_id, formatted_date, buyer_name, buyer_address, consignee_address, 
                                      buyer_gst, po_details, dispatch, total_price, final_amount])

        # Add invoices CSV to ZIP
        zip_file.writestr("invoices.csv", invoices_csv.getvalue())

        # Invoice Items CSV
        items_csv = StringIO()
        items_writer = csv.writer(items_csv, quoting=csv.QUOTE_MINIMAL, lineterminator='\n')

        # Write headers
        items_writer.writerow(["Item ID", "Invoice ID", "Description", "HSN Code", "Quantity", "Rate", "Price"])

        # Write data rows
        for row in items_data:
            items_writer.writerow(row)

        # Add invoice items CSV to ZIP
        zip_file.writestr("invoice_items.csv", items_csv.getvalue())

    zip_buffer.seek(0)

    # Send ZIP file as response
    return Response(zip_buffer.read(), mimetype="application/zip",
                    headers={"Content-Disposition": "attachment; filename=invoices.zip"})

    
@app.route('/delete_address/<int:address_id>', methods=['POST'])
@role_required('admin')
def delete_address(address_id):
    conn = None
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(**DB_PARAMS)
        cursor = conn.cursor()

        # Start transaction
        conn.autocommit = False

        # 1. First check if the address exists and get buyer_id
        cursor.execute("SELECT buyer_id FROM buyer_addresses WHERE address_id = %s", (address_id,))
        address_record = cursor.fetchone()
        
        if not address_record:
            flash('Address not found', 'error')
            return redirect(url_for('buyer_table_new'))
            
        buyer_id = address_record[0]

        # 2. Check if this is the only address for this buyer
        cursor.execute("SELECT COUNT(*) FROM buyer_addresses WHERE buyer_id = %s", (buyer_id,))
        address_count = cursor.fetchone()[0]

        if address_count == 1:
            flash('Cannot delete the last address of a buyer. Delete the buyer instead.', 'error')
            return redirect(url_for('buyer_table_new'))

        # 3. Get all invoices that use this address
        cursor.execute("SELECT invoice_id, consignee_id FROM invoices WHERE address_id = %s", (address_id,))
        invoices = cursor.fetchall()
        invoice_ids = [row[0] for row in invoices]
        
        # 4. Get unique consignee_ids from these invoices
        consignee_ids = list(set(row[1] for row in invoices if row[1] is not None))

        # 5. Delete invoice items for these invoices
        if invoice_ids:
            cursor.execute("DELETE FROM invoice_items WHERE invoice_id = ANY(%s)", (invoice_ids,))

        # 6. Delete the invoices
        cursor.execute("DELETE FROM invoices WHERE address_id = %s", (address_id,))

        # 7. Delete the address
        cursor.execute("DELETE FROM buyer_addresses WHERE address_id = %s", (address_id,))

        # 8. Check if any consignee addresses are now orphaned and delete them
        for consignee_id in consignee_ids:
            # Check if this consignee is used in any other invoices
            cursor.execute("SELECT COUNT(*) FROM invoices WHERE consignee_id = %s", (consignee_id,))
            if cursor.fetchone()[0] == 0:
                # Not used anywhere else, safe to delete
                cursor.execute("DELETE FROM consignee_addresses WHERE consignee_id = %s", (consignee_id,))

        # Commit transaction
        conn.commit()

        flash('Address and associated data deleted successfully', 'success')
        return redirect(url_for('buyer_table_new'))

    except Exception as e:
        # Rollback transaction in case of error
        if conn:
            conn.rollback()
        flash(f'Error deleting address: {str(e)}', 'error')
        return redirect(url_for('buyer_table_new'))

    finally:
        # Ensure connection is closed
        if conn:
            conn.close()

@app.route('/duplicate_invoice/<invoice_id>', methods=['GET'])
@role_required('admin')
def duplicate_invoice(invoice_id):
    # Decode the invoice_id from the URL
    decoded_invoice_id = invoice_id.replace('-', '/')
    decoded_invoice_id = replace_slash_with_hyphen(decoded_invoice_id)

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)

    # Fetch the original invoice details
    cursor.execute('''
        SELECT invoices.*, buyer_info.buyer_name, buyer_addresses.address, buyer_info.buyer_gst, consignee_addresses.consignee_address
        FROM invoices
        JOIN buyer_info ON invoices.buyer_id = buyer_info.buyer_id
        JOIN buyer_addresses ON invoices.address_id = buyer_addresses.address_id
        LEFT JOIN consignee_addresses ON invoices.consignee_id = consignee_addresses.consignee_id
        WHERE invoices.invoice_id = %s
    ''', (decoded_invoice_id,))
    original_invoice = cursor.fetchone()

    if original_invoice is None:
        return "Invoice not found", 404

    # Convert the DictCursor row to a regular dictionary
    original_invoice = dict(original_invoice)

    # Add consignee_details to the original_invoice dictionary
    original_invoice['consignee_details'] = original_invoice.get('consignee_address', '')

    # Fetch the invoice items
    cursor.execute('SELECT * FROM invoice_items WHERE invoice_id = %s', (decoded_invoice_id,))
    invoice_items = cursor.fetchall()

    # Fetch the next invoice number for the current financial year
    cursor.execute("SELECT MAX(invoice_id) FROM invoices WHERE invoice_id LIKE 'RMC / 24 - 25 / %'")
    last_invoice_id = cursor.fetchone()[0]

    if last_invoice_id:
        # Extract the numeric part of the last invoice ID (e.g., "008" from "RMC / 24 - 25 / 008")
        last_invoice_number = int(last_invoice_id.split('/')[-1].strip())
        next_inv = f"{last_invoice_number + 1:03}"
    else:
        # If no invoices exist for the current financial year, start from 1
        next_inv = "001"

    # Close the cursor and connection
    cursor.close()
    conn.close()

    # Financial year options
    financial_years = ['20 - 21', '21 - 22', '22 - 23', '23 - 24', '24 - 25']

    # Calculate total price and final amount for the original invoice
    total_price = sum(item['price'] for item in invoice_items)
    final_amount = total_price * 1.18  # Assuming 18% GST

    # Render the duplicate invoice template with pre-filled data
    return render_template(
        'duplicate_invoice.html',
        original_invoice=original_invoice,
        invoice_items=invoice_items,
        next_invoice_number=next_inv,
        financial_years=financial_years,
        total_price=total_price,
        final_amount=final_amount
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
