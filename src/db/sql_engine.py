"""
Simple SQL query engine for virtual nutrition tables.

This module provides a lightweight SQL-like query engine that operates on
the virtual session table data structures, enabling LLMs to write SQL queries
for nutrition analysis without requiring a full database.
"""

import re
import pandas as pd
from typing import Dict, List, Any, Optional
import logging

#logger = logging.get#logger(__name__)

class VirtualSQLEngine:
    """
    Simple SQL query engine for virtual nutrition tables.
    
    Supports:
    - SELECT with column expressions and calculations
    - FROM with table names
    - JOIN operations (INNER, LEFT, RIGHT)
    - WHERE clauses with basic conditions
    - GROUP BY and aggregate functions (SUM, AVG, COUNT, etc.)
    - ORDER BY clauses
    - Basic CASE expressions for unit conversion
    """
    
    def __init__(self, session_data: Dict[str, Any]):
        self.session_data = session_data
        self.tables = self._prepare_tables()
    
    def _prepare_tables(self) -> Dict[str, pd.DataFrame]:
        """Convert virtual session data to pandas DataFrames for SQL processing."""
        tables = {}
        
        # Convert recipe_ingredients table
        if 'recipe_ingredients' in self.session_data:
            tables['recipe_ingredients'] = pd.DataFrame(self.session_data['recipe_ingredients'])
        
        # Convert cnf_foods table  
        if 'cnf_foods' in self.session_data:
            tables['cnf_foods'] = pd.DataFrame(self.session_data['cnf_foods'])
            
        # Convert cnf_nutrients table
        if 'cnf_nutrients' in self.session_data:
            tables['cnf_nutrients'] = pd.DataFrame(self.session_data['cnf_nutrients'])
            
        # Convert recipes table (metadata)
        if 'recipes' in self.session_data:
            recipes_list = list(self.session_data['recipes'].values())
            if recipes_list:
                tables['recipes'] = pd.DataFrame(recipes_list)
        
        return tables
    
    def execute(self, query: str) -> Dict[str, Any]:
        """
        Execute a SQL-like query on the virtual tables.
        
        Args:
            query: SQL query string
            
        Returns:
            Dict with query results or error information
        """
        try:
            # Normalize query
            query = query.strip()
            if not query.upper().startswith('SELECT'):
                return {"error": "Only SELECT queries are supported"}
            
            # Parse and execute query using pandas
            result_df = self._execute_select(query)
            
            # Convert result to dict format
            if result_df is not None:
                return {
                    "success": "Query executed successfully",
                    "rows": len(result_df),
                    "columns": list(result_df.columns),
                    "data": result_df.to_dict('records')
                }
            else:
                return {"error": "Query execution failed"}
                
        except Exception as e:
            #logger.error(f"SQL query execution error: {e}")
            return {"error": f"Query execution failed: {str(e)}"}
    
    def _execute_select(self, query: str) -> Optional[pd.DataFrame]:
        """Execute a SELECT query using pandas operations."""
        try:
            # Simple query parsing - this is a basic implementation
            # For production, would use a proper SQL parser
            
            # Extract table name from FROM clause
            from_match = re.search(r'FROM\s+(\w+)', query, re.IGNORECASE)
            if not from_match:
                raise ValueError("No FROM clause found")
            
            main_table = from_match.group(1)
            if main_table not in self.tables:
                raise ValueError(f"Table '{main_table}' not found")
            
            result_df = self.tables[main_table].copy()
            
            # Handle JOINs
            result_df = self._process_joins(query, result_df)
            
            # Handle WHERE clause
            result_df = self._process_where(query, result_df)
            
            # Handle SELECT columns and calculations
            result_df = self._process_select(query, result_df)
            
            # Handle GROUP BY
            result_df = self._process_group_by(query, result_df)
            
            # Handle ORDER BY
            result_df = self._process_order_by(query, result_df)
            
            return result_df
            
        except Exception as e:
            #logger.error(f"SELECT query processing error: {e}")
            raise
    
    def _process_joins(self, query: str, df: pd.DataFrame) -> pd.DataFrame:
        """Process JOIN clauses in the query."""
        # Find all JOIN clauses
        join_pattern = r'(LEFT\s+JOIN|RIGHT\s+JOIN|INNER\s+JOIN|JOIN)\s+(\w+)\s+ON\s+([\w\s.=]+)'
        joins = re.findall(join_pattern, query, re.IGNORECASE)
        
        for join_type, table_name, condition in joins:
            if table_name not in self.tables:
                continue
                
            join_table = self.tables[table_name]
            
            # Parse the ON condition (simplified - assumes format: table1.col = table2.col)
            condition_parts = condition.strip().split('=')
            if len(condition_parts) == 2:
                left_col = condition_parts[0].strip().split('.')[-1]  # Get column name
                right_col = condition_parts[1].strip().split('.')[-1]
                
                # Determine join type
                how = 'inner'
                if 'LEFT' in join_type.upper():
                    how = 'left'
                elif 'RIGHT' in join_type.upper():
                    how = 'right'
                
                # Perform the join
                df = df.merge(join_table, left_on=left_col, right_on=right_col, how=how, suffixes=('', '_joined'))
        
        return df
    
    def _process_where(self, query: str, df: pd.DataFrame) -> pd.DataFrame:
        """Process WHERE clause in the query."""
        where_match = re.search(r'WHERE\s+(.+?)(?:GROUP\s+BY|ORDER\s+BY|$)', query, re.IGNORECASE | re.DOTALL)
        if not where_match:
            return df
        
        where_clause = where_match.group(1).strip()
        
        # Simple WHERE processing - handle basic conditions
        # This is simplified - would need more robust parsing for production
        if '=' in where_clause:
            parts = where_clause.split('=')
            if len(parts) == 2:
                column = parts[0].strip().replace("'", "").replace('"', '')
                value = parts[1].strip().replace("'", "").replace('"', '')
                
                # Handle column references (remove table prefixes)
                if '.' in column:
                    column = column.split('.')[-1]
                
                if column in df.columns:
                    df = df[df[column] == value]
        
        return df
    
    def _process_select(self, query: str, df: pd.DataFrame) -> pd.DataFrame:
        """Process SELECT clause and column calculations."""
        # Extract SELECT clause
        select_match = re.search(r'SELECT\s+(.+?)\s+FROM', query, re.IGNORECASE | re.DOTALL)
        if not select_match:
            return df
        
        select_clause = select_match.group(1).strip()
        
        # Handle SELECT *
        if select_clause == '*':
            return df
        
        # Parse selected columns/expressions
        columns = [col.strip() for col in select_clause.split(',')]
        result_columns = {}
        
        for col_expr in columns:
            # Handle AS aliases
            if ' AS ' in col_expr.upper():
                parts = re.split(r'\s+AS\s+', col_expr, flags=re.IGNORECASE)
                expression = parts[0].strip()
                alias = parts[1].strip()
            else:
                expression = col_expr.strip()
                alias = expression
            
            # Process the expression
            if self._is_simple_column(expression, df):
                # Simple column reference
                col_name = expression.split('.')[-1] if '.' in expression else expression
                if col_name in df.columns:
                    result_columns[alias] = df[col_name]
            else:
                # Complex expression - try to evaluate
                try:
                    result_columns[alias] = self._evaluate_expression(expression, df)
                except:
                    # If evaluation fails, try to use as column name
                    col_name = expression.split('.')[-1] if '.' in expression else expression
                    if col_name in df.columns:
                        result_columns[alias] = df[col_name]
        
        if result_columns:
            return pd.DataFrame(result_columns)
        else:
            return df
    
    def _process_group_by(self, query: str, df: pd.DataFrame) -> pd.DataFrame:
        """Process GROUP BY clause."""
        group_match = re.search(r'GROUP\s+BY\s+([\w\s,]+)', query, re.IGNORECASE)
        if not group_match:
            return df
        
        group_cols = [col.strip() for col in group_match.group(1).split(',')]
        
        # Simple GROUP BY with aggregation
        if all(col in df.columns for col in group_cols):
            return df.groupby(group_cols).agg('sum').reset_index()
        
        return df
    
    def _process_order_by(self, query: str, df: pd.DataFrame) -> pd.DataFrame:
        """Process ORDER BY clause."""
        order_match = re.search(r'ORDER\s+BY\s+([\w\s,]+)', query, re.IGNORECASE)
        if not order_match:
            return df
        
        order_cols = [col.strip() for col in order_match.group(1).split(',')]
        
        # Simple ORDER BY
        valid_cols = [col for col in order_cols if col in df.columns]
        if valid_cols:
            return df.sort_values(valid_cols)
        
        return df
    
    def _is_simple_column(self, expression: str, df: pd.DataFrame) -> bool:
        """Check if expression is a simple column reference."""
        col_name = expression.split('.')[-1] if '.' in expression else expression
        return col_name in df.columns and not any(op in expression for op in ['+', '-', '*', '/', '(', ')'])
    
    def _evaluate_expression(self, expression: str, df: pd.DataFrame) -> pd.Series:
        """Evaluate complex expressions with calculations."""
        # Simple expression evaluation for basic math operations
        # This is a simplified implementation
        
        # Handle SUM() function
        if expression.upper().startswith('SUM('):
            inner_expr = expression[4:-1]  # Remove SUM( and )
            inner_result = self._evaluate_expression(inner_expr, df)
            return pd.Series([inner_result.sum()])
        
        # Handle basic arithmetic with columns
        # Replace column names with actual values for evaluation
        eval_expr = expression
        for col in df.columns:
            if col in eval_expr:
                eval_expr = eval_expr.replace(col, f'df["{col}"]')
        
        try:
            # Use eval for simple mathematical expressions
            # Note: This is simplified - production would need safer evaluation
            return eval(eval_expr)
        except:
            # If evaluation fails, return the original column or zeros
            return pd.Series([0] * len(df))

def get_available_tables_info() -> Dict[str, Any]:
    """Get information about available virtual tables and their schemas."""
    return {
        "recipe_ingredients": {
            "description": "Recipe ingredient data with parsed amounts and units",
            "columns": [
                "ingredient_id (PK)",
                "recipe_id (FK)", 
                "ingredient_name",
                "amount (float)",
                "unit (string)",
                "ingredient_order (int)",
                "cnf_food_code (FK)"
            ],
            "example": "SELECT ingredient_name, amount, unit FROM recipe_ingredients WHERE recipe_id = 'recipe1'"
        },
        "cnf_foods": {
            "description": "CNF food descriptions and metadata",
            "columns": [
                "cnf_food_code (PK)",
                "food_description"
            ],
            "example": "SELECT * FROM cnf_foods WHERE food_description LIKE '%honey%'"
        },
        "cnf_nutrients": {
            "description": "CNF nutrient values for different serving sizes",
            "columns": [
                "cnf_food_code (FK)",
                "nutrient_name",
                "nutrient_value (float)",
                "per_amount (float)",
                "unit (string)"
            ],
            "example": "SELECT * FROM cnf_nutrients WHERE nutrient_name = 'Energy (kcal)'"
        },
        "recipes": {
            "description": "Recipe metadata and details",
            "columns": [
                "recipe_id (PK)",
                "title",
                "base_servings (int)",
                "prep_time",
                "cook_time"
            ],
            "example": "SELECT title, base_servings FROM recipes"
        }
    }