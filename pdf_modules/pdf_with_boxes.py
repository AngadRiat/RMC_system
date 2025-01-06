import fitz  # PyMuPDF
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from io import BytesIO

# Define the invoice data with multiple items
invoice_data = {
    "invoice_no": "RMC / 24 - 25 / 086",
    "invoice_date": "15.10.2024",
    "po_no_date": "K/PO/24-25/0133\n14.10.2024",
    "dispatched_by": "TCI FREIGHT",
    "buyer_details": "STP LIMITED\nD 16 & 17 UPSIDC Industrial Area, Kosi\nKotwan Uttar Pradesh 281403\nGSTIN 09AAECS6339M1ZR",
    "consignee_details": "STP LIMITED\nD 16 & 17 UPSIDC Industrial Area Kosi\nKotwan Uttar Pradesh 281403",
    "goods": [
        {"description": "3\" X 3\" All bearing type helical gear pump with base 3/4\" jacketed\nhi\nhi\nhi\nhi\nhi\nhi\nhi\nhi\nhi\nhi", "qty": "1", "hsn": "8413", "rate": "44,000.00", "amount": "44,000.00"},
        {"description": "Duplicate item for testing 3\" X 3\" All bearing type helical gear", "qty": "2", "hsn": "8413", "rate": "44,000.00", "amount": "88,000.00"}
    ],
    "igst": "18",
    "igst_amount": "7,920.00",
    "total_amount": "132,000.00",
    "grand_total": "155,920.00",
    "amount_in_words": "One hundred fifty-five thousand nine hundred twenty only"
}

# Step 1: Create an overlay PDF with the invoice data
overlay_pdf_stream = BytesIO()
c = canvas.Canvas(overlay_pdf_stream, pagesize=A4)

# Function to wrap text within box boundaries without cutting off words
def draw_wrapped_text(canvas, x, y, text, box_width, default_box_height, max_box_height, max_font_size=12):
    font_size = max_font_size
    box_height = default_box_height
    
    # Split text into paragraphs, and strip extra whitespace
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]

    # Fixed line height to control spacing precisely
    while font_size > 6:
        text_object = canvas.beginText(x + 2, y - 2)
        text_object.setFont("Helvetica", font_size)
        
        # Line height set slightly smaller than font size for tighter control
        line_height = font_size + 1  # Customize this to adjust spacing (try font_size only if +1 adds too much space)
        current_height = y
        lines = []

        # Process paragraphs for wrapping and avoid blank lines
        for paragraph in paragraphs:
            words = paragraph.split()
            line = ""
            for word in words:
                if canvas.stringWidth(line + " " + word, "Helvetica", font_size) <= box_width:
                    line += " " + word if line else word
                else:
                    lines.append(line)
                    line = word
            if line:
                lines.append(line)  # Add last line of the paragraph without extra line break

        # Calculate required height for all lines
        required_height = len(lines) * line_height
        if required_height <= box_height:
            for line in lines:
                # Only draw non-empty lines to avoid extra line space
                if line:
                    text_object.setTextOrigin(x + 2, current_height - line_height)
                    text_object.textLine(line)
                current_height -= line_height
            canvas.drawText(text_object)
            canvas.setStrokeColor(colors.black)
            canvas.rect(x, y - box_height, box_width, box_height, stroke=1, fill=0)
            return box_height  # Return actual height used by the text box
        else:
            if box_height < max_box_height:
                box_height = min(box_height + 5, max_box_height)
            else:
                font_size -= 0.5

    return box_height  # Return the final box height if text overflowed


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

            # Draw the text and bounding box
            canvas.drawString(text_x, text_y, text)
            canvas.setStrokeColor(colors.black)
            canvas.rect(x, y - box_height, box_width, box_height, stroke=1, fill=0)
            return
        else:
            font_size -= 0.5

# Draw fixed details
draw_wrapped_text(c, 310, 765, invoice_data["invoice_no"], box_width=120, default_box_height=20, max_box_height=20)
draw_wrapped_text(c, 310, 750, invoice_data["invoice_date"], box_width=100, default_box_height=20, max_box_height=20)
draw_wrapped_text(c, 475, 760, invoice_data["po_no_date"], box_width=100, default_box_height=35, max_box_height=35)
draw_wrapped_text(c, 360, 705, invoice_data["dispatched_by"], box_width=150, default_box_height=30, max_box_height=30)
draw_wrapped_text(c, 35, 655, invoice_data["buyer_details"], box_width=250, default_box_height=58, max_box_height=58)
draw_wrapped_text(c, 305, 655, invoice_data["consignee_details"], box_width=270, default_box_height=58, max_box_height=58)

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
draw_centered_text(c, 421, 233, invoice_data["igst"], box_width=25, box_height=20)
draw_centered_text(c, 475, 233, invoice_data["igst_amount"], box_width=105, box_height=20)
draw_centered_text(c, 475, 193, invoice_data["grand_total"], box_width=105, box_height=20)
draw_wrapped_text(c, 75, 193, invoice_data["amount_in_words"], box_width=280, default_box_height=38, max_box_height=38)

c.showPage()
c.save()
overlay_pdf_stream.seek(0)

template_path = "data/Tax Invoice 2024 TEMPLATE.pdf"
output_path = "data/filled_invoice_with_auto_adjusting_text_boxes.pdf"
template_pdf = fitz.open(template_path)
overlay_pdf = fitz.open("pdf", overlay_pdf_stream)
page = template_pdf[0]
page.show_pdf_page(page.rect, overlay_pdf, 0)
template_pdf.save(output_path)
template_pdf.close()
overlay_pdf.close()

print(f"Filled invoice with auto-adjusting text boxes saved to {output_path}")
