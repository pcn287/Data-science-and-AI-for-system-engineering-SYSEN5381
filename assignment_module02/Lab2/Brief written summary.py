# Brief written summary
The app shows methane (CH₄) emissions from GreenFeed 453 using C-lock visit data. 
You choose an animal and a date in the sidebar; the By date view shows the average CH₄ (Gram/day) 
for that combination in a card plus a table of all visits, and the Average by animal view shows a 
Plotly bar chart of average CH₄ per animal for that date with the selected animal highlighted. 
Data is either loaded from CSVs in the downloaded GF files folder or refreshed from the C-lock API (with credentials in a .env file),
and the app always uses the data from that folder.