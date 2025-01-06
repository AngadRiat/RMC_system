import os
import sqlite3
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
from datetime import datetime
from werkzeug.security import check_password_hash
import csv
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)

# MISC Functions used

# Function to convert YYYY-MM-DD to DD/MM/YYYY
def format_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")

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
    conn = sqlite3.connect('RMC_Sales_new.db')
    conn.row_factory = sqlite3.Row  # Enable dictionary-like row access
    return conn

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
    x = invoice_data["invoice_no"]
    y = x.split("/")
    z = y[0] + "-" + y[1] + "-" + y[2]
    output_path = "data/invoices/" + z + ".pdf"
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
    
    # Save and close PDFs
    new_pdf.save(output_path)
    template_pdf.close()
    overlay_pdf.close()
    new_pdf.close()

    print(f"PDF with multiple pages saved to {output_path}")

    # Load the saved PDF for storing in the database as BLOB
    with open(output_path, "rb") as f:
        pdf_data = f.read()

    # Return the binary data to be stored in the database
    return pdf_data


# PAGE ROUTINGS

# Authentication and Roles
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        # Fetch the user by username only, no password in the SQL query
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        # Check if user exists and verify the password hash
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['username']
            session['role'] = user['role']
            session['user_name'] = user['name']
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
    
    # Fetching all invoices and their items from the database
    invoices = conn.execute('SELECT * FROM invoices').fetchall()
    invoice_items = conn.execute('SELECT * FROM invoice_items').fetchall()
    
    # Create a dictionary to hold the structured invoice data
    invoice_data = []

    # Group the invoice items by invoice_id
    items_by_invoice = {}
    
    for item in invoice_items:
        if item['invoice_id'] not in items_by_invoice:
            items_by_invoice[item['invoice_id']] = []
        items_by_invoice[item['invoice_id']].append({
            'itemID': item['item_id'],
            'description': item['description'],
            'hsnCode': item['hsn_code'],
            'quantity': item['quantity'],
            'rate': item['rate'],
            'price': item['price']
        })
    
    # Organize invoices and their associated items
    for invoice in invoices:
        # Fetch buyer details
        buyer_name = conn.execute('SELECT buyer_name FROM buyer_info WHERE buyer_id = ?', (invoice["buyer_id"],)).fetchone()
        buyer_gst = conn.execute('SELECT buyer_gst FROM buyer_info WHERE buyer_id = ?', (invoice["buyer_id"],)).fetchone()
        buyer_address = conn.execute('SELECT address FROM buyer_addresses WHERE address_id = ?', (invoice["address_id"],)).fetchone()

        # Access the actual value from each fetch result tuple
        buyer_name = buyer_name[0] if buyer_name else "Unknown"
        buyer_gst = buyer_gst[0] if buyer_gst else "N/A"
        buyer_address = buyer_address[0] if buyer_address else "No Address"

        invoice_data.append({
            'invoiceID': invoice['invoice_id'],
            'buyerName': buyer_name,
            'invoiceDate': format_date(invoice['invoice_date']),
            'poDetails': invoice['po_details'],
            'buyerAddress': buyer_address,
            'gstin': buyer_gst,
            'consignee': invoice['consignee_details'],
            'dispatch': invoice['dispatch'],
            'totalPrice': invoice['total_price'],
            'finalAmount': invoice['final_amount'],
            'items': items_by_invoice.get(invoice['invoice_id'], [])
        })

    conn.close()
    # Passing the structured data to the template
    return render_template('view_invoices_new.html', invoice_data=invoice_data, format_indian_currency=format_indian_currency, user_role=session.get("role"))

@app.route('/first_page_new')
@role_required('admin')
def first_page_new():
    # Get buyer_id and address_id from request arguments
    buyer_id = request.args.get('buyer_id')
    address_id = request.args.get('address_id')
    buyer_info = None
    selected_address = None
    buyer_addresses = []

    conn = get_db_connection()

    if buyer_id:
        cursor = conn.cursor()
        
        # Fetch buyer name and GST details from the database for the specified buyer_id
        cursor.execute("SELECT buyer_name, buyer_gst FROM buyer_info WHERE buyer_id = ?", (buyer_id,))
        result = cursor.fetchone()
        if result:
            buyer_info = {
                'buyer_name': result[0],
                'buyer_gst': result[1]
            }
        
        # Retrieve all associated addresses for the buyer
        cursor.execute("SELECT address_id, address FROM buyer_addresses WHERE buyer_id = ?", (buyer_id,))
        buyer_addresses = [{'address_id': addr[0], 'address': addr[1]} for addr in cursor.fetchall()]

        # Set the selected address if address_id is provided
        if address_id:
            cursor.execute("SELECT address FROM buyer_addresses WHERE address_id = ?", (address_id,))
            selected_address = cursor.fetchone()
            if selected_address:
                selected_address = selected_address[0]  # Get address string from fetched tuple

    # Close the database connection
    conn.close()

    # Render the template, passing buyer info, selected address, and all addresses
    return render_template(
        'first_page_new.html',
        buyer_info=buyer_info,
        selected_address=selected_address,
        buyer_addresses=buyer_addresses
    )


# Second page (form input) routing
@app.route('/second_page_new', methods=['POST'])
@role_required('admin')
def second_page_new():
    # Storing form data in session variables
    year = request.form["year"]
    inv_id = request.form["inv_no"]
    session["Invoice_ID"] = ("RMC / " + year + " / " + inv_id)
    
    conn = get_db_connection()
    existing_invoice = conn.execute('SELECT * FROM invoices WHERE invoice_id = ?', (session["Invoice_ID"],)).fetchone()
    conn.close()
    
    if existing_invoice:
        flash('Invoice number already exists. Please enter a unique invoice number.', 'error')
        return redirect(url_for('first_page_new'))
    
    session["Date"] = request.form["date"]
    if (request.form["po"])=="":
        session["PO_Details"]= None
    else:
        session["PO_Details"] = request.form["po"]
    if (request.form["d_by"])=="":
        session["Dispatch"]= None
    else:
        session["Dispatch"] = request.form["d_by"]
    session["Buyer_Name"] = request.form["b_name"]
    session["Buyer_Address"] = request.form["b_address"]
    session["Buyer_GST"] = request.form["b_gst"]
    session["Consignee"] = request.form["c_details"]
    
    buyer_address = session["Buyer_Address"]
    buyer_state = extract_state_from_address(buyer_address)
    session["Buyer_State"] = buyer_state
    
    if not buyer_state:
        flash('Please include a valid Indian state in the buyer address.', 'error')
        return redirect(url_for('first_page_new'))
    
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
    no_of_items = int(request.form["n_items"])
    items = []
    total_price = 0

    # Process each item entered in the form
    for i in range(1, no_of_items + 1):
        item = {
            'description': request.form[f'description{i}'],
            'hsnCode': request.form[f'hsnCode{i}'],
            'qty': int(request.form[f'qty{i}']),
            'rate': int(request.form[f'rate{i}']),
            'price': int(request.form[f'qty{i}']) * int(request.form[f'rate{i}']),
        }
        items.append(item)
        total_price += item['price']  # Accumulate total price for all items

    # Store items and total price in session for later use in submit_invoice routing
    session["Items"] = items
    session["Total_Price"] = total_price

    # Calculate applicable taxes based on the buyer's state
    igst = 0
    cgst = 0
    sgst = 0
    final_amount = total_price

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

    # Store final calculated amount and tax details in session
    session["final_amount"] = final_amount
    session["cgst"] = cgst
    session["sgst"] = sgst
    session["igst"] = igst

    # Render third_page_new.html with all the required data
    return render_template(
        'third_page_new.html',
        items=list(enumerate(items, start=1)),
        company_name="Riat Machinery Co.",
        buyer_name=session["Buyer_Name"],
        invoice_date=format_date(session["Date"]),
        invoice_id=session["Invoice_ID"],
        dispatch_details=session["Dispatch"],
        cgst=cgst,
        sgst=sgst,
        igst=igst,
        buyer_address=buyer_address,
        buyer_gst=session["Buyer_GST"],
        consignee=session["Consignee"],
        final_amount=final_amount,
        total_price=total_price,
        po_details=session["PO_Details"]
    )

# start here next day

# Submit invoice (form input) routing
@app.route('/submit_invoice_new', methods=['POST'])
@role_required('admin')
def submit_invoice_new():
    # Fetch data from session to insert into the database
    conn = get_db_connection()

    # Check if the buyer exists in buyer_info and fetch the buyer_id if it does
    cursor = conn.execute('SELECT buyer_id FROM buyer_info WHERE buyer_name = ?', (session["Buyer_Name"],))
    result = cursor.fetchone()

    if result:
        # Existing buyer: fetch the buyer_id
        buyer_id = result[0]
        # Update buyer's GSTIN if needed
        conn.execute('''
            UPDATE buyer_info 
            SET buyer_gst = ? 
            WHERE buyer_id = ?''',
            (session["Buyer_GST"], buyer_id))
    else:
        # New buyer: insert into buyer_info and fetch buyer_id
        conn.execute('''INSERT INTO buyer_info (buyer_name, buyer_gst) VALUES (?, ?)''',
                     (session["Buyer_Name"], session["Buyer_GST"]))
        conn.commit()
        buyer_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    # Check if buyer's address already exists in buyer_addresses and fetch address_id
    cursor = conn.execute('SELECT address_id FROM buyer_addresses WHERE buyer_id = ? AND address = ?', (buyer_id, session["Buyer_Address"]))
    address_result = cursor.fetchone()

    if address_result:
        # Existing address: fetch the address_id
        address_id = address_result[0]
    else:
        # New address: insert into buyer_addresses and fetch address_id
        conn.execute('''INSERT INTO buyer_addresses (buyer_id, address) VALUES (?, ?)''',
                     (buyer_id, session["Buyer_Address"]))
        conn.commit()
        address_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

    # Insert invoice data into invoices table, linking to buyer_id and address_id
    conn.execute('''INSERT INTO invoices (invoice_id, invoice_date, buyer_id, address_id, po_details, consignee_details, dispatch,
                  total_price, final_amount) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (session["Invoice_ID"], session["Date"], buyer_id, address_id, session["PO_Details"],
                  session["Consignee"], session["Dispatch"], session["Total_Price"], session["final_amount"]))

    # Insert each item into invoice_items table linked to this invoice
    print(session["Items"])
    for item in session["Items"]:
        conn.execute('''INSERT INTO invoice_items 
                        (invoice_id, description, hsn_code, quantity, rate, price) 
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (session["Invoice_ID"], item['description'], item['hsnCode'], item['qty'], item['rate'], item['price']))

    # Commit the changes and close the connection
    conn.commit()
    conn.close()

    # Redirect to the invoice generation page
    return redirect(url_for('generate_invoice_new', invoice_id=session["Invoice_ID"].replace('/', '-')))


# Generate pdf page routing
@app.route('/generate_invoice_new/<invoice_id>', methods=['GET'])
@role_required('admin')
def generate_invoice_new(invoice_id):
    conn = get_db_connection()

    # Decode the invoice_id from the URL
    decoded_invoice_id = invoice_id.replace('-', '/')
    invoice_id = replace_slash_with_hyphen(decoded_invoice_id)
    
    # Fetch invoice, item data, buyer, and address data
    invoice = conn.execute('SELECT * FROM invoices WHERE invoice_id = ?', (invoice_id,)).fetchone()
    items = conn.execute('SELECT * FROM invoice_items WHERE invoice_id = ?', (invoice_id,)).fetchall()
    
    # Get buyer_id from the invoice and retrieve buyer info and address details
    buyer_info = conn.execute('SELECT * FROM buyer_info WHERE buyer_id = ?', (invoice["buyer_id"],)).fetchone()
    buyer_address = conn.execute('SELECT * FROM buyer_addresses WHERE address_id = ?', (invoice["address_id"],)).fetchone()
    
    if not invoice or not buyer_info or not buyer_address:
        return jsonify({"error": "Invoice or buyer details not found"}), 404
    
    # Calculate IGST/CGST/SGST and amount in words
    total_price = invoice["total_price"]
    amount_in_words = convert_amount_to_words(invoice["final_amount"])
    print(session["Buyer_State"])

    if session["Buyer_State"].lower() == "west bengal":
        cgst_amount = total_price * 0.09
        sgst_amount = total_price * 0.09

        invoice_data = {
            "invoice_no": f"{invoice['invoice_id']}",
            "invoice_date": format_date(invoice["invoice_date"]),
            "po_no_date": f"{invoice['po_details']}",
            "dispatched_by": invoice["dispatch"],
            "buyer_details": f"{buyer_info['buyer_name']}\n{buyer_address['address']}\nGSTIN {buyer_info['buyer_gst']}",
            "buyer_state": session["Buyer_State"].lower(),
            "consignee_details": invoice["consignee_details"],
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
            "invoice_no": f"{invoice['invoice_id']}",
            "invoice_date": format_date(invoice["invoice_date"]),
            "po_no_date": f"{invoice['po_details']}",
            "dispatched_by": invoice["dispatch"],
            "buyer_details": f"{buyer_info['buyer_name']}\n{buyer_address['address']}\nGSTIN {buyer_info['buyer_gst']}",
            "buyer_state": session["Buyer_State"].lower(),
            "consignee_details": invoice["consignee_details"],
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
    
    print(invoice_data)
    # Generate PDF
    pdf_data = pdf_generate_new(invoice_data)

    # Store PDF as BLOB in the database
    conn.execute('UPDATE invoices SET pdf_invoice = ? WHERE invoice_id = ?', (pdf_data, invoice_id))
    conn.commit()
    conn.close()
    
    # Retain user_id and role in session, clear other session data
    user_id = session["user_id"]
    role = session["role"]
    session.clear()
    session["user_id"] = user_id
    session["role"] = role
    
    # Redirect to a confirmation page or another view, e.g., invoice details
    return render_template('invoice_submitted_new.html', invoice_no=invoice_data["invoice_no"])


@app.route('/edit_invoice_new/<invoice_id>', methods=['GET', 'POST'])
@role_required('admin')
def edit_invoice_new(invoice_id):
    # Decode the invoice_id from the URL
    decoded_invoice_id = invoice_id.replace('-', '/')
    decoded_invoice_id = replace_slash_with_hyphen(decoded_invoice_id)

    conn = get_db_connection()

    # Fetch invoice, buyer, and address details based on decoded_invoice_id
    invoice = conn.execute('''
        SELECT invoices.*, buyer_info.buyer_name, buyer_addresses.address, buyer_info.buyer_gst
        FROM invoices
        JOIN buyer_info ON invoices.buyer_id = buyer_info.buyer_id
        JOIN buyer_addresses ON invoices.address_id = buyer_addresses.address_id
        WHERE invoices.invoice_id = ?
    ''', (decoded_invoice_id,)).fetchone()

    invoice_items = conn.execute('SELECT * FROM invoice_items WHERE invoice_id = ?', (decoded_invoice_id,)).fetchall()

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
        consignee_details = request.form['consignee_details']
        dispatch = request.form.get('dispatch', None)
        total_price = float(request.form['total_price'])
        final_amount = float(request.form['final_amount'])

        # Update each invoice item based on the form submission
        for item in invoice_items:
            item_id = item['item_id']
            description = request.form[f'description_{item_id}']
            hsn_code = request.form[f'hsnCode_{item_id}']
            qty = int(request.form[f'quantity_{item_id}'])
            rate = float(request.form[f'rate_{item_id}'])
            price = qty * rate

            # Update the invoice item details in the 'invoice_items' table
            conn.execute('''
                UPDATE invoice_items 
                SET description = ?, hsn_code = ?, quantity = ?, rate = ?, price = ? 
                WHERE item_id = ? AND invoice_id = ?''',
                (description, hsn_code, qty, rate, price, item_id, decoded_invoice_id))

        # Check if the new buyer name exists in `buyer_info`
        new_buyer = conn.execute('SELECT * FROM buyer_info WHERE buyer_name = ?', (buyer_name,)).fetchone()

        if new_buyer:
            # If the new buyer exists, check if the address needs to be updated or a new address entry is needed
            new_buyer_id = new_buyer['buyer_id']
            existing_address = conn.execute(
                'SELECT * FROM buyer_addresses WHERE buyer_id = ? AND address = ?',
                (new_buyer_id, buyer_address)).fetchone()
            conn.execute('''UPDATE buyer_info
                         SET buyer_gst = ?
                         WHERE buyer_id = ?''',
                         (buyer_gst,new_buyer_id))
            if not existing_address:
                # Insert new address for this buyer if it doesn’t exist
                conn.execute('''
                    INSERT INTO buyer_addresses (buyer_id, address)
                    VALUES (?, ?)''',
                    (new_buyer_id, buyer_address))
                address_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            else:
                # Use the existing address
                address_id = existing_address['address_id']

            # Update the invoice with the new buyer_id and address_id
            conn.execute('''
                UPDATE invoices 
                SET buyer_id = ?, address_id = ?, invoice_date = ?, total_price = ?, final_amount = ?, po_details = ?, 
                    consignee_details = ?, dispatch = ?
                WHERE invoice_id = ?''',
                (new_buyer_id, address_id, invoice_date, total_price, final_amount, po_details, 
                 consignee_details, dispatch, decoded_invoice_id))

        else:
            # If buyer does not exist, create a new buyer and address entry
            conn.execute('''
                INSERT INTO buyer_info (buyer_name, buyer_gst)
                VALUES (?, ?)''', (buyer_name, buyer_gst))
            
            new_buyer_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            # Insert new address for this buyer
            conn.execute('''
                INSERT INTO buyer_addresses (buyer_id, address)
                VALUES (?, ?)''', (new_buyer_id, buyer_address))
            address_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]

            # Update the invoice with the new buyer_id and address_id
            conn.execute('''
                UPDATE invoices 
                SET buyer_id = ?, address_id = ?, invoice_date = ?, total_price = ?, final_amount = ?, po_details = ?, 
                    consignee_details = ?, dispatch = ?
                WHERE invoice_id = ?''',
                (new_buyer_id, address_id, invoice_date, total_price, final_amount, po_details, 
                 consignee_details, dispatch, decoded_invoice_id))

        # Commit the changes and close the connection
        conn.commit()
        conn.close()

        # After updating, redirect back to the invoice view page
        return redirect(url_for('generate_invoice_new', invoice_id=decoded_invoice_id.replace('/', '-')))

    conn.close()
    print(invoice)
    # For GET requests, render the edit page with the invoice data pre-filled
    return render_template('edit_invoice_new.html', invoice=invoice, invoice_items=invoice_items, format_indian_currency=format_indian_currency)

@app.route('/view_pdf_new/<invoice_id>')
def view_pdf_new(invoice_id):
    # Replace '-' with '/' if invoice IDs are stored in the database with slashes
    invoice_id = invoice_id.replace('-', '/')
    invoice_id = replace_slash_with_hyphen(invoice_id)

    # Connect to the database and query for the PDF data
    try:
        conn = sqlite3.connect("RMC_Sales_new.db")
        cursor = conn.cursor()
        cursor.execute("SELECT pdf_invoice FROM invoices WHERE invoice_id = ?", (invoice_id,))
        result = cursor.fetchone()
    finally:
        conn.close()

    # Check if a result was found
    if result and result[0]:
        pdf_data = result[0]
        return Response(io.BytesIO(pdf_data), mimetype='application/pdf')
    else:
        return "PDF not found for this invoice.", 404
    
@app.route('/buyer_table_new')
def buyer_table_new():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch buyer information along with multiple addresses for each buyer
    cursor.execute('''
        SELECT buyer_info.buyer_id, buyer_info.buyer_name, buyer_info.buyer_gst, buyer_addresses.address, buyer_addresses.address_id
        FROM buyer_info
        LEFT JOIN buyer_addresses ON buyer_info.buyer_id = buyer_addresses.buyer_id
        ORDER BY buyer_info.buyer_id
    ''')
    
    # Fetch all rows and close the connection
    raw_data = cursor.fetchall()
    conn.close()

    # Organize data by buyer_id to group addresses
    buyers = {}
    for row in raw_data:
        buyer_id, buyer_name, buyer_gst, address, address_id = row
        if buyer_id not in buyers:
            buyers[buyer_id] = {
                'buyer_name': buyer_name,
                'buyer_gst': buyer_gst,
                'addresses': [],
                'address_id' : []
            }
        if address:
            buyers[buyer_id]['addresses'].append(address)
            buyers[buyer_id]['address_id'].append(address_id)

    # Pass the data to the buyer_table.html template
    return render_template('buyer_table_new.html', buyers=buyers, user_role=session.get("role"))

@app.route('/delete_invoice_new/<invoice_id>', methods=['POST'])
@role_required('admin')
def delete_invoice_new(invoice_id):
    # Convert the invoice_id to match the database format if necessary
    decoded_invoice_id = invoice_id.replace('-', '/')
    decoded_invoice_id = replace_slash_with_hyphen(decoded_invoice_id)

    conn = get_db_connection()

    try:
        # Begin a transaction to ensure both deletions succeed or fail together
        conn.execute('BEGIN')
        
        # Delete associated items from the invoice_items table
        conn.execute('DELETE FROM invoice_items WHERE invoice_id = ?', (decoded_invoice_id,))
        
        # Delete the invoice from the invoices table
        conn.execute('DELETE FROM invoices WHERE invoice_id = ?', (decoded_invoice_id,))
        
        # Commit the transaction if both deletions are successful
        conn.commit()
    except Exception as e:
        # Roll back the transaction in case of an error
        conn.rollback()
        # Log the error and return a 500 status with an error message
        return f"Error deleting invoice: {e}", 500
    finally:
        # Close the database connection
        conn.close()

    # Redirect back to the view invoices page after successful deletion
    return redirect(url_for('view_invoices_new'))

@app.route('/delete_buyer_new/<buyer_id>', methods=['POST'])
@role_required('admin')
def delete_buyer_new(buyer_id):
    conn = get_db_connection()
    
    try:
        # Begin a transaction to ensure all deletions succeed or fail together
        conn.execute('BEGIN')
        
        # Delete associated invoices and invoice items for this buyer
        conn.execute('DELETE FROM invoice_items WHERE invoice_id IN (SELECT invoice_id FROM invoices WHERE buyer_id = ?)', (buyer_id,))
        conn.execute('DELETE FROM invoices WHERE buyer_id = ?', (buyer_id,))
        
        # Delete the addresses associated with this buyer
        conn.execute('DELETE FROM buyer_addresses WHERE buyer_id = ?', (buyer_id,))
        
        # Delete the buyer from the buyer_info table
        conn.execute('DELETE FROM buyer_info WHERE buyer_id = ?', (buyer_id,))
        
        # Commit the transaction if all deletions are successful
        conn.commit()
    except Exception as e:
        # Roll back the transaction in case of an error
        conn.rollback()
        return f"Error deleting buyer: {e}", 500
    finally:
        # Close the database connection
        conn.close()

    # Redirect back to the buyer table page after successful deletion
    return redirect(url_for('buyer_table_new'))


@app.route('/check_buyer', methods=['POST'])
@role_required('admin')
def check_buyer():
    data = request.get_json()
    buyer_name = data.get('buyer_name')
    
    conn = get_db_connection()
    # Fetch buyer_id, GST, and associated addresses
    buyer = conn.execute('SELECT buyer_id, buyer_gst FROM buyer_info WHERE buyer_name = ?', (buyer_name,)).fetchone()
    
    if buyer:
        buyer_id = buyer['buyer_id']
        buyer_gst = buyer['buyer_gst']
        # Fetch all addresses associated with the buyer_id
        addresses = conn.execute('SELECT address FROM buyer_addresses WHERE buyer_id = ?', (buyer_id,)).fetchall()
        conn.close()

        # Convert the list of addresses to a simpler format for JSON response
        address_list = [address['address'] for address in addresses]
        
        return jsonify({
            'exists': True,
            'buyer_gst': buyer_gst,
            'addresses': address_list
        })
    else:
        conn.close()
        return jsonify({'exists': False})
    
@app.route('/export_invoices_csv')
def export_invoices_csv():
    # Connect to the SQLite database
    conn = get_db_connection()
    cursor = conn.cursor()

    # SQL query to fetch the required data with correct joins
    cursor.execute("""
        SELECT i.invoice_id, i.invoice_date, b.buyer_name, ba.address, b.buyer_gst, 
               i.po_details, i.consignee_details, i.dispatch, i.total_price, i.final_amount
        FROM invoices i
        JOIN buyer_info b ON i.buyer_id = b.buyer_id
        JOIN buyer_addresses ba ON i.address_id = ba.address_id
        ORDER BY i.invoice_id ASC
    """)

    # Fetch the data
    data = cursor.fetchall()

    # Close the database connection
    conn.close()

    # Use StringIO to write CSV data
    output = StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow(["Invoice ID", "Invoice Date", "Buyer Name", "Buyer Address", "Buyer GST",
                     "PO Details", "Consignee Details", "Dispatch Details", "Total Price", "Final Amount"])
    
    # Write data rows with formatted date
    for row in data:
        invoice_id, invoice_date, buyer_name, buyer_address, buyer_gst, po_details, consignee_details, dispatch, total_price, final_amount = row
        # Convert invoice_date to DD/MM/YYYY format if it's in YYYY-MM-DD
        formatted_date = datetime.strptime(invoice_date, "%Y-%m-%d").strftime("%d/%m/%Y") if invoice_date else ""
        writer.writerow([invoice_id, formatted_date, buyer_name, buyer_address, buyer_gst, po_details, 
                         consignee_details, dispatch, total_price, final_amount])

    # Get the CSV string from StringIO
    csv_data = output.getvalue()
    output.close()

    # Send CSV as downloadable file
    return Response(csv_data, mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=invoices.csv"})
    
@app.route('/delete_address/<int:address_id>', methods=['POST'])
def delete_address(address_id):
    conn = get_db_connection()
    try:
        # Delete all invoice items associated with invoices having this address_id
        conn.execute("DELETE FROM invoice_items WHERE invoice_id IN (SELECT invoice_id FROM invoices WHERE address_id = ?)", (address_id,))
        # Delete all invoices associated with this address_id
        conn.execute("DELETE FROM invoices WHERE address_id = ?", (address_id,))
        # Delete the address itself
        conn.execute("DELETE FROM buyer_addresses WHERE address_id = ?", (address_id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        return f"Error deleting addewss: {e}", 500
    finally:
        # Close the database connection
        conn.close()
        
    return redirect(url_for('buyer_table_new'))

if __name__ == '__main__':
    app.run(debug=True)
