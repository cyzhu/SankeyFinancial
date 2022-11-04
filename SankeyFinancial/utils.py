from sec_edgar_api import EdgarClient
import pandas as pd
from functools import reduce
import plotly.graph_objects as go
from typing import Union
import os

#! Only tested on AAPL financial statement for now
class GetData:
    def __init__(
        self,
        your_company_name:str,
        your_company_email:str,
        cik:str,
        company_ticker:str,
        taxonomy:str="us-gaap",
        period:str = "Y",
        scaledown:int = 1e6,
        ) -> None:
        self.edgar = EdgarClient(user_agent=f"{your_company_name} {your_company_email}")
        if period == "Y":
            self.form_list = ["10-K",'10-K/A']
        elif period == "Q":
            # self.form_list = ["10-Q"]
            raise NotImplementedError("Will be implemented soon!")
        else:
            raise NotImplementedError("Only supporting period = 'Y' or 'Q' for now.")

        self.cik = cik
        # ToDo: could match automatically
        self.company_ticker = company_ticker
        self.taxonomy = taxonomy
        self.scaledown = scaledown
        if scaledown == 1e6:
            self.scale_suffix = "M"
        elif scaledown == 1e3:
            self.scale_suffix = "k"
        else:
            raise NotImplementedError("Only supporting scaledown value M and k now.")

        self.tags = [
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "CostOfGoodsAndServicesSold",
            "GrossProfit",
            "OperatingExpenses",
            "OperatingIncomeLoss",
            "NonoperatingIncomeExpense",
            "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
            "IncomeTaxExpenseBenefit",
            "NetIncomeLoss",
        ]
        self.labels = [
            "Revenue",
            "Cost of Sales",
            "Gross Profit",
            "Operating Expense",
            "Operating Profit",
            "Other Income",
            "Pre-tax Profit",
            "Tax",
            "Net Income",
        ]
        self._concat_data()
        self.yr = None

    def _get_df_by_tag(self, tag:str, label:str, form_list:list=None, scale_down = 1e6):
        """_summary_

        Parameters
        ----------
        tag : str
            _description_
        label : str
            _description_
        form_list : list, optional
            Could be a list of items of ['10-K', '10-K/A', '10-Q', '8-K'], by default None

        Returns
        -------
        _type_
            _description_
        """
        if form_list is None:
            form_list = ["10-K",'10-K/A']
        t0 = self.edgar.get_company_concept(cik=self.cik, taxonomy=self.taxonomy, tag=tag)
        df = pd.DataFrame(t0['units']['USD'])
        df = df.loc[df['form'].isin(form_list),:]
        df['val'] = (df['val']/scale_down).astype(int)
        df.rename(columns={"val":label},inplace=True)
        return df.reset_index(drop=True)

    def _get_node_label(self,value_text,label):
        #ToDo: Need to figure out if this is AAPL specific.
        pre1 = label+"<br>"+value_text
        if "Profit" in label or label in ("Net Income","Tax"):
            rt = int(round(self.df_trans.loc[self.df_trans['label']==label,'val'].values[0]*100/self.revenue,0))
            if "Gross" in label:
                prefix = "Gross margin"
            elif label == "Tax":
                prefix = "Tax rate"
            else:
                prefix = "Margin"
            pre1 = pre1+f"<br>{prefix}: {rt}%"
        return pre1

    def _concat_data(self):
        df_list = [self._get_df_by_tag(
            t,l,form_list = self.form_list,
            scale_down= self.scaledown
            ) for t,l in zip(self.tags,self.labels)]

        cols_join = [col for col in df_list[0].columns if col != self.labels[0]]
        df_final = reduce(lambda left, right: pd.merge(left, right, on=cols_join, how='inner'), df_list)
        self.df_final = df_final.loc[~df_final['frame'].isnull(),:]

    def _prepare_sankey_data(self):
        # ToDo: this is just year, doesn't have quarterly support yet
        df_trans = self.df_final.loc[self.df_final['frame']==f'CY{self.yr}',self.labels].T
        df_trans.columns = ['val']
        df_trans.reset_index(inplace=True)
        df_trans.rename(columns={"index":'label'},inplace=True)
        df_trans.reset_index(inplace=True)

        self.revenue = df_trans.loc[0,"val"]
        self.vals_txt = df_trans['val'].map(lambda x: "${:,}".format(x)+self.scale_suffix).to_list()

        df_trans = df_trans.iloc[1:]
        # flow other income is reversed, manually set it
        df_trans['source'] = [0,0,2,2,5,4,6,6]
        df_trans.loc[df_trans['source']==5,'index'] = 6

        df_trans['color_link_hex'] = ['#666666','#0088cc']*2+['#0088cc']*2+['#666666','#0088cc']
        df_trans['color_link'] = df_trans['color_link_hex'].apply(lambda x: color_transform(x))

        self.df_trans = df_trans

    def _prepare_fig(self):
        color_labels = ['#0088cc']+['#666666','#0088cc']*2+['#0088cc']*2+['#666666','#0088cc']
        steps = 1/4
        nodes_x = [0]+[steps]*2+[steps*2]*2+[steps*2.5,steps*3]+[steps*4]*2
        nodes_y = [0.3,0.8,0.25,0.7,0.2,0.5,0.2,0.5,0.05]

        link = dict(
            source = self.df_trans['source'], 
            target = self.df_trans['index'],
            value = self.df_trans['val'],
            color = self.df_trans['color_link']
        )
        node = dict(
            # label = labels,
            pad = 15, 
            thickness = 20,
            color = color_labels,
            x = nodes_x,
            y = nodes_y,
        )
        data = go.Sankey(
            link = link, 
            node=node,
            valueformat = "$,",
            valuesuffix = self.scale_suffix,
            arrangement='snap',
        )
        fig = go.Figure(data)

        for x,y,txt,nl in zip(nodes_x,nodes_y,self.vals_txt,self.labels):
            fig.add_annotation(
                    x=x-0.02,
                    #ToDo: I think the auto adjustment for y is to count the length of the bar
                    y=1-y,
                    text=self._get_node_label(txt,nl),
                    showarrow=False,
                    align="center",
                    )

        fig.update_layout(
            hovermode = 'x',
            title=f"Financial Statement - Apple {self.yr}",
            font=dict(size = 11),
        )
        self.fig = fig
    
    def prepare(self, yr:int):
        self.yr = yr
        self._prepare_sankey_data()
        self._prepare_fig()
    
    def show(self, save_as:Union[None, str] = None,path:str = None):
        if save_as is None:
            self.fig.show()
        else:
            if path is None:
                path = os.getcwd()
            if save_as == "html":
                self.fig.write_html(f"{path}/{self.company_ticker}{self.yr}.html")
            elif save_as == "png":
                self.fig.write_image(
                    f"{path}/{self.company_ticker}{self.yr}.png",
                    scale =2)

def color_transform(x:str,alpha = 0.5):
    h = x.lstrip('#')
    rgb = tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    rgba = f"rgba({rgb[0]},{rgb[1]},{rgb[2]},{alpha})"
    return rgba