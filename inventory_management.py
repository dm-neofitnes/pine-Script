#!/usr/bin/env python3
"""
Inventory Management System
A comprehensive system for managing inventory with SQLite database backend.
"""

import sqlite3
from datetime import datetime
from typing import Optional, List, Tuple
import json


class InventoryDatabase:
    """Handles all database operations for the inventory system."""
    
    def __init__(self, db_path: str = "inventory.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()
    
    def create_tables(self):
        """Create necessary database tables."""
        cursor = self.conn.cursor()
        
        # Categories table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Products table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sku TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                category_id INTEGER,
                quantity INTEGER DEFAULT 0,
                min_quantity INTEGER DEFAULT 0,
                price REAL DEFAULT 0.0,
                cost REAL DEFAULT 0.0,
                location TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        ''')
        
        # Transaction history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                transaction_type TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                previous_quantity INTEGER,
                new_quantity INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        ''')
        
        self.conn.commit()
    
    def close(self):
        """Close database connection."""
        self.conn.close()


class Category:
    """Category management class."""
    
    def __init__(self, db: InventoryDatabase):
        self.db = db
    
    def add(self, name: str, description: str = "") -> int:
        """Add a new category."""
        cursor = self.db.conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO categories (name, description) VALUES (?, ?)",
                (name, description)
            )
            self.db.conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError(f"Category '{name}' already exists")
    
    def get_all(self) -> List[sqlite3.Row]:
        """Get all categories."""
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT * FROM categories ORDER BY name")
        return cursor.fetchall()
    
    def get_by_id(self, category_id: int) -> Optional[sqlite3.Row]:
        """Get category by ID."""
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT * FROM categories WHERE id = ?", (category_id,))
        return cursor.fetchone()
    
    def delete(self, category_id: int) -> bool:
        """Delete a category."""
        cursor = self.db.conn.cursor()
        cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        self.db.conn.commit()
        return cursor.rowcount > 0


class Product:
    """Product management class."""
    
    def __init__(self, db: InventoryDatabase):
        self.db = db
    
    def add(self, sku: str, name: str, description: str = "", 
            category_id: Optional[int] = None, quantity: int = 0,
            min_quantity: int = 0, price: float = 0.0, 
            cost: float = 0.0, location: str = "") -> int:
        """Add a new product."""
        cursor = self.db.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO products 
                (sku, name, description, category_id, quantity, min_quantity, price, cost, location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (sku, name, description, category_id, quantity, min_quantity, price, cost, location))
            
            self.db.conn.commit()
            
            # Log transaction
            product_id = cursor.lastrowid
            self._log_transaction(product_id, "INITIAL", quantity, 0, quantity, "Initial stock")
            
            return product_id
        except sqlite3.IntegrityError:
            raise ValueError(f"Product with SKU '{sku}' already exists")
    
    def update(self, product_id: int, **kwargs) -> bool:
        """Update product information."""
        allowed_fields = ['sku', 'name', 'description', 'category_id', 'quantity', 
                         'min_quantity', 'price', 'cost', 'location']
        
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return False
        
        updates['updated_at'] = datetime.now()
        
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        values = list(updates.values()) + [product_id]
        
        cursor = self.db.conn.cursor()
        
        # Check if quantity is being updated
        if 'quantity' in updates:
            old_quantity = self.get_by_id(product_id)['quantity']
            new_quantity = updates['quantity']
            cursor.execute(
                "UPDATE products SET " + set_clause + " WHERE id = ?",
                values
            )
            self.db.conn.commit()
            self._log_transaction(product_id, "ADJUSTMENT", 
                                new_quantity - old_quantity, old_quantity, new_quantity,
                                "Manual quantity adjustment")
        else:
            cursor.execute(
                "UPDATE products SET " + set_clause + " WHERE id = ?",
                values
            )
            self.db.conn.commit()
        
        return cursor.rowcount > 0
    
    def delete(self, product_id: int) -> bool:
        """Delete a product."""
        cursor = self.db.conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        self.db.conn.commit()
        return cursor.rowcount > 0
    
    def get_by_id(self, product_id: int) -> Optional[sqlite3.Row]:
        """Get product by ID."""
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT p.*, c.name as category_name 
            FROM products p 
            LEFT JOIN categories c ON p.category_id = c.id 
            WHERE p.id = ?
        """, (product_id,))
        return cursor.fetchone()
    
    def get_by_sku(self, sku: str) -> Optional[sqlite3.Row]:
        """Get product by SKU."""
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT p.*, c.name as category_name 
            FROM products p 
            LEFT JOIN categories c ON p.category_id = c.id 
            WHERE p.sku = ?
        """, (sku,))
        return cursor.fetchone()
    
    def get_all(self) -> List[sqlite3.Row]:
        """Get all products."""
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT p.*, c.name as category_name 
            FROM products p 
            LEFT JOIN categories c ON p.category_id = c.id 
            ORDER BY p.name
        """)
        return cursor.fetchall()
    
    def search(self, search_term: str) -> List[sqlite3.Row]:
        """Search products by name, SKU, or description."""
        cursor = self.db.conn.cursor()
        search_pattern = f"%{search_term}%"
        cursor.execute("""
            SELECT p.*, c.name as category_name 
            FROM products p 
            LEFT JOIN categories c ON p.category_id = c.id 
            WHERE p.name LIKE ? OR p.sku LIKE ? OR p.description LIKE ?
            ORDER BY p.name
        """, (search_pattern, search_pattern, search_pattern))
        return cursor.fetchall()
    
    def get_low_stock(self) -> List[sqlite3.Row]:
        """Get products with quantity below minimum."""
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT p.*, c.name as category_name 
            FROM products p 
            LEFT JOIN categories c ON p.category_id = c.id 
            WHERE p.quantity <= p.min_quantity
            ORDER BY p.quantity
        """)
        return cursor.fetchall()
    
    def _log_transaction(self, product_id: int, trans_type: str, 
                        quantity: int, prev_qty: int, new_qty: int, notes: str = ""):
        """Log a transaction."""
        cursor = self.db.conn.cursor()
        cursor.execute('''
            INSERT INTO transactions 
            (product_id, transaction_type, quantity, previous_quantity, new_quantity, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (product_id, trans_type, quantity, prev_qty, new_qty, notes))
        self.db.conn.commit()


class InventoryManager:
    """Main inventory management class."""
    
    def __init__(self, db_path: str = "inventory.db"):
        self.db = InventoryDatabase(db_path)
        self.categories = Category(self.db)
        self.products = Product(self.db)
    
    def add_stock(self, product_id: int, quantity: int, notes: str = "") -> bool:
        """Add stock to a product."""
        product = self.products.get_by_id(product_id)
        if not product:
            return False
        
        new_quantity = product['quantity'] + quantity
        cursor = self.db.conn.cursor()
        cursor.execute(
            "UPDATE products SET quantity = ?, updated_at = ? WHERE id = ?",
            (new_quantity, datetime.now(), product_id)
        )
        self.db.conn.commit()
        
        self.products._log_transaction(
            product_id, "STOCK_IN", quantity, 
            product['quantity'], new_quantity, notes
        )
        return True
    
    def remove_stock(self, product_id: int, quantity: int, notes: str = "") -> bool:
        """Remove stock from a product."""
        product = self.products.get_by_id(product_id)
        if not product or product['quantity'] < quantity:
            return False
        
        new_quantity = product['quantity'] - quantity
        cursor = self.db.conn.cursor()
        cursor.execute(
            "UPDATE products SET quantity = ?, updated_at = ? WHERE id = ?",
            (new_quantity, datetime.now(), product_id)
        )
        self.db.conn.commit()
        
        self.products._log_transaction(
            product_id, "STOCK_OUT", -quantity,
            product['quantity'], new_quantity, notes
        )
        return True
    
    def get_transaction_history(self, product_id: Optional[int] = None) -> List[sqlite3.Row]:
        """Get transaction history, optionally filtered by product."""
        cursor = self.db.conn.cursor()
        if product_id:
            cursor.execute("""
                SELECT t.*, p.name as product_name, p.sku as product_sku
                FROM transactions t
                JOIN products p ON t.product_id = p.id
                WHERE t.product_id = ?
                ORDER BY t.created_at DESC
            """, (product_id,))
        else:
            cursor.execute("""
                SELECT t.*, p.name as product_name, p.sku as product_sku
                FROM transactions t
                JOIN products p ON t.product_id = p.id
                ORDER BY t.created_at DESC
            """)
        return cursor.fetchall()
    
    def get_inventory_value(self) -> dict:
        """Calculate total inventory value."""
        cursor = self.db.conn.cursor()
        cursor.execute("""
            SELECT 
                SUM(quantity * cost) as total_cost,
                SUM(quantity * price) as total_retail,
                SUM(quantity) as total_items
            FROM products
        """)
        row = cursor.fetchone()
        return {
            'total_cost': row['total_cost'] or 0,
            'total_retail': row['total_retail'] or 0,
            'total_items': row['total_items'] or 0,
            'potential_profit': (row['total_retail'] or 0) - (row['total_cost'] or 0)
        }
    
    def close(self):
        """Close database connection."""
        self.db.close()


def main():
    """CLI interface for the inventory management system."""
    import sys
    
    manager = InventoryManager()
    
    print("=" * 60)
    print("INVENTORY MANAGEMENT SYSTEM")
    print("=" * 60)
    
    while True:
        print("\n--- Main Menu ---")
        print("1. View All Products")
        print("2. Add New Product")
        print("3. Update Product")
        print("4. Delete Product")
        print("5. Search Products")
        print("6. Add Stock")
        print("7. Remove Stock")
        print("8. View Low Stock Alerts")
        print("9. View Categories")
        print("10. Add Category")
        print("11. Transaction History")
        print("12. Inventory Value Report")
        print("13. Exit")
        
        choice = input("\nEnter your choice (1-13): ").strip()
        
        try:
            if choice == '1':
                products = manager.products.get_all()
                if products:
                    print(f"\n{'ID':<5} {'SKU':<15} {'Name':<25} {'Qty':<8} {'Price':<10} {'Category':<15}")
                    print("-" * 80)
                    for p in products:
                        cat = p['category_name'] or 'N/A'
                        print(f"{p['id']:<5} {p['sku']:<15} {p['name']:<25} {p['quantity']:<8} ${p['price']:<9.2f} {cat:<15}")
                else:
                    print("\nNo products found.")
            
            elif choice == '2':
                sku = input("Enter SKU: ").strip()
                name = input("Enter product name: ").strip()
                desc = input("Enter description (optional): ").strip()
                
                # Show categories
                categories = manager.categories.get_all()
                if categories:
                    print("\nAvailable categories:")
                    for c in categories:
                        print(f"  {c['id']}. {c['name']}")
                    cat_id = input("Enter category ID (or leave blank): ").strip()
                    cat_id = int(cat_id) if cat_id else None
                else:
                    cat_id = None
                
                qty = int(input("Enter initial quantity: ") or 0)
                min_qty = int(input("Enter minimum quantity: ") or 0)
                price = float(input("Enter selling price: ") or 0)
                cost = float(input("Enter cost: ") or 0)
                location = input("Enter location (optional): ").strip()
                
                product_id = manager.products.add(sku, name, desc, cat_id, qty, min_qty, price, cost, location)
                print(f"\n✓ Product added successfully with ID: {product_id}")
            
            elif choice == '3':
                product_id = int(input("Enter product ID to update: "))
                product = manager.products.get_by_id(product_id)
                if not product:
                    print("Product not found!")
                    continue
                
                print(f"\nCurrent: {product['name']} (SKU: {product['sku']})")
                print("Leave blank to keep current value")
                
                name = input(f"New name [{product['name']}]: ").strip() or product['name']
                sku = input(f"New SKU [{product['sku']}]: ").strip() or product['sku']
                desc = input(f"New description [{product['description'] or 'N/A'}]: ").strip()
                desc = desc if desc else product['description']
                
                updates = {'name': name, 'sku': sku, 'description': desc}
                
                price = input(f"New price [{product['price']}]: ").strip()
                if price:
                    updates['price'] = float(price)
                
                cost = input(f"New cost [{product['cost']}]: ").strip()
                if cost:
                    updates['cost'] = float(cost)
                
                manager.products.update(product_id, **updates)
                print("\n✓ Product updated successfully!")
            
            elif choice == '4':
                product_id = int(input("Enter product ID to delete: "))
                product = manager.products.get_by_id(product_id)
                if product:
                    confirm = input(f"Are you sure you want to delete '{product['name']}'? (y/n): ")
                    if confirm.lower() == 'y':
                        manager.products.delete(product_id)
                        print("\n✓ Product deleted successfully!")
                else:
                    print("Product not found!")
            
            elif choice == '5':
                term = input("Enter search term: ").strip()
                results = manager.products.search(term)
                if results:
                    print(f"\nFound {len(results)} product(s):")
                    print(f"{'ID':<5} {'SKU':<15} {'Name':<25} {'Qty':<8} {'Price':<10}")
                    print("-" * 70)
                    for p in results:
                        print(f"{p['id']:<5} {p['sku']:<15} {p['name']:<25} {p['quantity']:<8} ${p['price']:<9.2f}")
                else:
                    print("\nNo products found matching your search.")
            
            elif choice == '6':
                product_id = int(input("Enter product ID: "))
                product = manager.products.get_by_id(product_id)
                if product:
                    qty = int(input("Enter quantity to add: "))
                    notes = input("Enter notes (optional): ").strip()
                    if manager.add_stock(product_id, qty, notes):
                        print(f"\n✓ Added {qty} units to '{product['name']}'")
                        print(f"  New quantity: {product['quantity'] + qty}")
                else:
                    print("Product not found!")
            
            elif choice == '7':
                product_id = int(input("Enter product ID: "))
                product = manager.products.get_by_id(product_id)
                if product:
                    qty = int(input(f"Enter quantity to remove (available: {product['quantity']}): "))
                    notes = input("Enter notes (optional): ").strip()
                    if manager.remove_stock(product_id, qty, notes):
                        print(f"\n✓ Removed {qty} units from '{product['name']}'")
                        print(f"  New quantity: {product['quantity'] - qty}")
                    else:
                        print("\n✗ Insufficient stock!")
                else:
                    print("Product not found!")
            
            elif choice == '8':
                low_stock = manager.products.get_low_stock()
                if low_stock:
                    print(f"\n⚠️  LOW STOCK ALERT ({len(low_stock)} items):")
                    print(f"{'ID':<5} {'SKU':<15} {'Name':<25} {'Qty':<8} {'Min':<8}")
                    print("-" * 70)
                    for p in low_stock:
                        print(f"{p['id']:<5} {p['sku']:<15} {p['name']:<25} {p['quantity']:<8} {p['min_quantity']:<8}")
                else:
                    print("\n✓ All products are adequately stocked!")
            
            elif choice == '9':
                categories = manager.categories.get_all()
                if categories:
                    print(f"\n{'ID':<5} {'Name':<25} {'Description':<30}")
                    print("-" * 60)
                    for c in categories:
                        desc = c['description'] or 'N/A'
                        print(f"{c['id']:<5} {c['name']:<25} {desc:<30}")
                else:
                    print("\nNo categories found.")
            
            elif choice == '10':
                name = input("Enter category name: ").strip()
                desc = input("Enter description (optional): ").strip()
                try:
                    cat_id = manager.categories.add(name, desc)
                    print(f"\n✓ Category added successfully with ID: {cat_id}")
                except ValueError as e:
                    print(f"\n✗ Error: {e}")
            
            elif choice == '11':
                product_id = input("Enter product ID for history (or leave blank for all): ").strip()
                if product_id:
                    product_id = int(product_id)
                history = manager.get_transaction_history(product_id if product_id else None)
                if history:
                    print(f"\nTransaction History:")
                    print(f"{'ID':<5} {'Product':<20} {'Type':<12} {'Qty':<8} {'Date':<20}")
                    print("-" * 70)
                    for t in history[:20]:  # Show last 20
                        print(f"{t['id']:<5} {t['product_name'][:20]:<20} {t['transaction_type']:<12} {t['quantity']:<8} {t['created_at']:<20}")
                else:
                    print("\nNo transactions found.")
            
            elif choice == '12':
                value = manager.get_inventory_value()
                print("\n" + "=" * 40)
                print("INVENTORY VALUE REPORT")
                print("=" * 40)
                print(f"Total Items:        {value['total_items']:>10}")
                print(f"Total Cost Value:   ${value['total_cost']:>12,.2f}")
                print(f"Total Retail Value: ${value['total_retail']:>12,.2f}")
                print(f"Potential Profit:   ${value['potential_profit']:>12,.2f}")
                print("=" * 40)
            
            elif choice == '13':
                print("\nThank you for using Inventory Management System!")
                break
            
            else:
                print("\n✗ Invalid choice. Please enter a number between 1 and 13.")
        
        except ValueError as e:
            print(f"\n✗ Error: {e}")
        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
    
    manager.close()


if __name__ == "__main__":
    main()
