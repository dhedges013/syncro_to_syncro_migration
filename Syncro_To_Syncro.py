#from syncro_utils import syncro_api_call
from pprint import pprint
from typing import Any, Dict, List
import requests
import time

from syncro_configs import get_logger

# Define API keys and subdomains for the tenants

#old Tenant
syncro_tenant_source_api_key = "API_KEY"
syncro_tenant_source_base_url = "https://SUBDOMAIN.syncromsp.com/api/v1"

#New Tenant
syncro_tenant_dest_api_key = "API_KEY"
syncro_tenant_dest_base_url = "https://SUBDOMAIN.syncromsp.com/api/v1"


logger = get_logger(__name__)
logger.info("Starting Syncro to Syncro Migration Script...")
logger.info(f"Source Tenant: {syncro_tenant_source_base_url}")
logger.info(f"Destination Tenant: {syncro_tenant_dest_base_url}")   

def syncro_api_call(api_key: str, base_url: str, endpoint: str, method: str = "GET", data: Any = None) -> Dict[str, Any]:
    """
    Make an API call to a Syncro tenant.

    Args:
        api_key (str): The API key for authorization.
        base_url (str): The base URL of the Syncro tenant.
        endpoint (str): The API endpoint to call.
        method (str): The HTTP method (GET, POST, etc.). Defaults to "GET".
        data (Any): The payload for POST/PUT requests. Defaults to None.

    Returns:
        Dict[str, Any]: The JSON response from the API call.
    """
    import requests
    time.sleep(.5)
    url = f"{base_url}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    response = requests.request(method, url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()

def get_all_customers(api_key: str, base_url: str) -> List[Dict[str, Any]]:
    """
    Retrieves all customers from Syncro API, handling pagination.

    Args:
        api_key (str): The API key for authorization.
        base_url (str): The base URL of the Syncro tenant.

    Returns:
        List[Dict[str, Any]]: A list of all customer records.
    """
    all_customers = []
    page = 1

    while True:
        endpoint = f"/customers?page={page}"
        response = syncro_api_call(api_key, base_url, endpoint)

        if "customers" in response:
            all_customers.extend(response["customers"])

        if "meta" in response and response["meta"]["page"] < response["meta"]["total_pages"]:
            page += 1
            time.sleep(0.5)  # Respect rate limits
        else:
            break

    return all_customers


def gather_and_compare_customers():
    """
    Gather and Compare Customer Lists
    If the newer Tenant is missing a match, creates a matching customer
    """
 # Fetch all customers for both tenants
    source_customers_list = get_all_customers(syncro_tenant_source_api_key, syncro_tenant_source_base_url)
    logger.info(f"Source Customers: {len(source_customers_list)}")

    dest_customers_list = get_all_customers(syncro_tenant_dest_api_key, syncro_tenant_dest_base_url)
    logger.info(f"Destination Customers: {len(dest_customers_list)}")

     # Extract 'business_name' from each customer dictionary in the source tenant
    business_names_source = [
        customer.get("business_name", "Unknown")
        for customer in source_customers_list
    ]

    # Extract 'business_name' from each customer dictionary in the destination tenant
    business_names_dest = [
        customer.get("business_name", "Unknown")
        for customer in dest_customers_list
    ]


    logger.info(f"Business Names in Source Tenant: {business_names_source}")
    logger.info(f"Business Names in Destination Tenant: {business_names_dest}") 

    missing_businesses = [
        name for name in business_names_source if name not in business_names_dest
    ]
    
    logger.warning(f"❌ Warning! Number of Mssing: {len(missing_businesses)} Missing businesses to be created: {missing_businesses}")

    for business_name in missing_businesses:
        # Prepare data for creating a new business
        new_business_data = {"business_name": business_name}

        # Create the missing business
        try:
            response = syncro_api_call(
                api_key=syncro_tenant_dest_api_key,
                base_url=syncro_tenant_dest_base_url,
                endpoint="customers",
                method="POST",
                data=new_business_data
            )
            
            logger.info(f"Created business: {business_name}, Response: {response}")
        except Exception as e:
            print(f"Failed to create business: {business_name}, Error: {e}")
            logger.error(f"Failed to create business: {business_name}, Error: {e}")

    return source_customers_list, dest_customers_list




def syncro_create_dest_ticket(ticket: Dict[str, Any],dest_customer_id: int) -> None:
    """
    Creates a new ticket in the destination Syncro tenant.

    Args:
        ticket (Dict[str, Any]): The ticket details to be created.

    Returns:
        None
    """
    logger.info(f"Creating ticket '{ticket['subject']}' in destination tenant...")
    # Fetch the corresponding customer ID in the destination tenant
    customer_name = ticket.get("customer_business_then_name")

    # Prepare the ticket data for creation
    ticket_payload = {
        "customer_id": dest_customer_id,
        "subject": ticket["subject"],
        "status": ticket["status"] if ticket["status"] else "New",
        "created_at": ticket["created_at"],
        "priority": "2 Normal",  
        "comments_attributes": []
    }
    """
    # Handle ticket comments if available
    if ticket.get("comments"):
        ##pprint(ticket.get("comments"))
        
        ticket_payload["comments_attributes"] = [
            {
                "subject": comment.get("subject", "Imported Comment"),
                "body": comment.get("body", ""),
                "hidden": comment.get("hidden", False),
                "do_not_email": comment.get("do_not_email", True),
                "tech": comment.get("tech", "None"),
                "created_at": comment["created_at"]
            }
            for comment in ticket["comments"] if isinstance(ticket["comments"], list)
        ]

        ticket_payload["comments_attributes"] = ticket.get("comments")
    """
        

    # Create the ticket in the destination tenant
    try:
        response = syncro_api_call(
            api_key=syncro_tenant_dest_api_key,
            base_url=syncro_tenant_dest_base_url,
            endpoint="tickets",
            method="POST",
            data=ticket_payload
        )
        logger.info(f"Created ticket '{ticket['subject']}' for customer '{customer_name}' in destination. Response: {response}")

        # Create ticket comments in the destination tenant
        for comment in ticket.get("comments", []):
            comment_payload = {                 
                "subject": comment.get("subject", "Imported Comment"),
                "body": comment.get("body", ""),
                "hidden": comment.get("hidden", False),
                "do_not_email": comment.get("do_not_email", True),
                "tech": comment.get("tech", "None"),
                "created_at": comment["created_at"]
            }

            syncro_create_ticket_comment(response["ticket"]["id"], comment_payload)
                
        logger.info(f"Created comments for ticket '{ticket['subject']}' in destination. Response: {response}")

    except Exception as e:
        logger.error(f"Failed to create ticket '{ticket['subject']}' for '{customer_name}': {e}")


def syncro_create_ticket_comment(ticket_id: int, comment_data: Dict[str, Any]):
    endpoint = f"/tickets/{ticket_id}/comment"
    response = syncro_api_call(
        api_key=syncro_tenant_dest_api_key,
        base_url=syncro_tenant_dest_base_url,
        endpoint=endpoint,
        method="POST",
        data=comment_data
    )


def syncro_get_customer_tickets(api_key: str, base_url: str, customer_id: int) -> Dict[str, Any]:
    """
    Fetch all tickets for a specific customer in a Syncro tenant.

    Args:
        api_key (str): The API key for authorization.
        base_url (str): The base URL of the Syncro tenant.
        customer_id (int): The customer ID to fetch tickets for.

    Returns:
        Dict[str, Any]: The JSON response containing the customer's tickets.
    """
    return syncro_api_call(
        api_key=api_key,
        base_url=base_url,
        endpoint=f"tickets?customer_id={customer_id}"
        
    )  


def syncro_lookup_dest_customer_id(customer_name: str,dest_customers):
    """
    Lookup the ID of a customer in the destination tenant.

    Args:
        customer_name (str): The name of the customer to lookup.

    Returns:
        int: The customer ID if found, otherwise None.
    """
    for customer in dest_customers:
        if customer.get("business_name") == customer_name:
            return customer.get("id"), customer.get("business_name")
    return None

def myfunction(source_customers, dest_customers):

    logger.info(f"in myfunction, Source Customers: {len(source_customers)}")
    #print(f"sourc_customers: {source_customers[0]}")
    #input("Press Enter to Continue...")
    for customer in source_customers:        
        source_customer_name = customer.get("business_name")
        source_customer_id = customer.get("id")
        logger.info(f"Processing source customer: {customer.get('business_name')}, Source Customer ID: {source_customer_id}")
        logger.info(f"Checking if customer '{source_customer_name}' exists in destination tenant...")
        dest_customer_id, dest_customer_name = syncro_lookup_dest_customer_id(source_customer_name,dest_customers)

        if dest_customer_id:
            logger.info(f"Source Customer '{source_customer_name}' found in destination tenant. with ID: {dest_customer_id} and name: {dest_customer_name}. Fetching tickets...")

            dest_customer_tickets = syncro_get_customer_tickets(
                api_key=syncro_tenant_dest_api_key,
                base_url=syncro_tenant_dest_base_url,
                customer_id=dest_customer_id
            )
            logger.info(f"dest_customer_name: '{dest_customer_name}' has {len(dest_customer_tickets.get('tickets', []))} tickets in destination tenant.")

            source_customer_tickets = syncro_get_customer_tickets(
                api_key=syncro_tenant_source_api_key,
                base_url=syncro_tenant_source_base_url,
                customer_id=source_customer_id
            )            
            logger.info(f"source_customer_name: '{source_customer_name}' has {len(source_customer_tickets.get('tickets', []))} tickets in source tenant.")

            for source_ticket in source_customer_tickets.get("tickets", []):
                source_ticket_subject = source_ticket.get("subject")
                logger.info(f"Gathering ticket '{source_ticket_subject}' from source tenant...")

                # Flag to track if a match is found
                ticket_exists = False

                for dest_ticket in dest_customer_tickets.get("tickets", []):
                    dest_ticket_subject = dest_ticket.get("subject")
                    logger.info(f"Checking ticket source '{source_ticket_subject}' in destination tenant... dest_ticket_subject: {dest_ticket_subject}")
                    
                    if source_ticket_subject == dest_ticket_subject:
                        logger.info(f"Ticket '{source_ticket_subject}' already exists in destination tenant. Skipping...")
                        ticket_exists = True
                        break  # Stop checking further once a match is found
                    # Ensure we only create a ticket if no match was found
                if ticket_exists:
                    continue  # Move to the next source ticket without creating one
                # If no match was found, create the ticket
                if not ticket_exists:
                    logger.info(f"'{source_ticket_subject}' not found in destination tenant. Creating ticket...")
                    logger.info(f"{source_ticket}")
                    #pprint(source_ticket)
                    #input("Press Enter to Continue...")
                    syncro_create_dest_ticket(source_ticket, dest_customer_id)
                 

def gather_and_compare_tickets():
    """
    Gather and compare ticket lists
    If the newer tenant is missing tickets, create the ticket
    Create a Contact if assigned Contact is not in the new account
    Continues with a warning if things like ticket status, issue type, or custom type are not the same
    """
    # Helper function to handle pagination
    from typing import List, Dict, Any
    def fetch_all_tickets(api_key: str, base_url: str) -> List[Dict[str, Any]]:
        tickets = []
        page = 1
        while True:
            response = syncro_api_call(
                api_key=api_key,
                base_url=base_url,
                endpoint=f"tickets?page={page}"
            )
            ticket_data = response.get("tickets", [])
            if not ticket_data:
                break  # Exit loop if no more tickets
            tickets.extend(ticket_data)
            page += 1
        return tickets

    logger.info("Fetching number of tickets from both tenants. comparing tickets...")
    # Fetch tickets from both tenants
    source_tickets = fetch_all_tickets(syncro_tenant_source_api_key, syncro_tenant_source_base_url)    
    dest_tickets = fetch_all_tickets(syncro_tenant_dest_api_key, syncro_tenant_dest_base_url)
    

    # Extract relevant ticket details for comparison
    source_ticket_list = [{
        "created_at": ticket.get("created_at"),
        "id": ticket.get("id"),
        "subject": ticket.get("subject"),
        "customer_business": ticket.get("customer_business_then_name"),
        "resolved_at": ticket.get("resolved_at"),
        "status": ticket.get("status"),
        "problem_type": ticket.get("problem_type"),
        "comments": ticket.get("comments")        
        } for ticket in source_tickets
    ]
    dest_ticket_list = [{
        "created_at": ticket.get("created_at"),
        "id": ticket.get("id"),
        "subject": ticket.get("subject"),
        "customer_business": ticket.get("customer_business_then_name"),
        "resolved_at": ticket.get("resolved_at"),
        "status": ticket.get("status"),
        "problem_type": ticket.get("problem_type"),
        "comments": ticket.get("comments")
        } for ticket in dest_tickets
    ]

    # Print ticket lists for verification
    logger.info(f"Number Source Tenant Tickets: {len(source_ticket_list)}")
    logger.info(f"Number Destination Tenant Tickets: {len(dest_ticket_list)}")

    # Use tuples of (subject, created_at, customer_business) for comparison
    dest_ticket_keys = {(ticket["subject"], ticket['customer_business']) for ticket in dest_ticket_list}
    tickets_to_create = []

    for ticket in source_ticket_list:
        ticket_key = (ticket["subject"], ticket['customer_business'])
        if ticket_key not in dest_ticket_keys:       
            tickets_to_create.append(ticket)
            logger.info(f"Ticket to be created: {ticket['customer_business']}, {ticket['subject']}, {ticket['created_at']}")

    logger.info(f"Number of Tickets to be created: {len(tickets_to_create)}")
    #input("Review the Logs and Press Enter to Continue...")


def check_if_contact_exists():
    pass


if __name__ == "__main__":
    source_customers, dest_customers = gather_and_compare_customers()
    gather_and_compare_tickets()
    myfunction(source_customers, dest_customers)