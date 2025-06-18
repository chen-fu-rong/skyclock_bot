class NavigationManager:
    def __init__(self, db):
        self.db = db
    
    def push_state(self, user_id, state):
        stack = self.db.get_user_nav_stack(user_id)
        stack.append(state)
        # Keep only last 5 states
        stack = stack[-5:]
        self.db.update_user_nav_stack(user_id, stack)
        return stack
    
    def pop_state(self, user_id):
        stack = self.db.get_user_nav_stack(user_id)
        if len(stack) > 1:
            stack.pop()  # Remove current state
            prev_state = stack[-1] if stack else "main_menu"  # Get new current state
            self.db.update_user_nav_stack(user_id, stack)
            return prev_state
        return "main_menu"  # Default state
    
    def current_state(self, user_id):
        stack = self.db.get_user_nav_stack(user_id)
        return stack[-1] if stack else "main_menu"